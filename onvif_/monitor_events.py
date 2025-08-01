from __future__ import annotations

import os
import uuid
import asyncio
import datetime as dt
import logging

from flask_socketio import SocketIO

import onvif
from onvif import ONVIFCamera
from onvif.exceptions import ONVIFError
from onvif.util import stringify_onvif_error
from zeep.exceptions import Fault, TransportError, XMLParseError
from zeep.exceptions import ValidationError # Ensure this is imported for CREATE_ERRORS

import utils.state as state
from utils.config import CONFIG
from utils.event_handler import EventHandler
from objects.ice_event import ICEEvent
from objects.ice_queue import ICEEventQueue
from onvif_.event_parser import ONVIFEvent, parse_event_message

log = logging.getLogger(__name__)

# Constants for subscription management
SUBSCRIPTION_TIME = dt.timedelta(minutes=10)
PULLPOINT_POLL_TIME = dt.timedelta(seconds=1) # How long to wait for messages in one pull request
PULLPOINT_MESSAGE_LIMIT = 100 # Max messages to pull at once
SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR = 1 # Seconds to wait before retrying on error

# ONVIF Error types
SUBSCRIPTION_ERRORS = (Fault, TimeoutError, TransportError)
CREATE_ERRORS = (
    ONVIFError,
    Fault,
    asyncio.TimeoutError,
    XMLParseError,
    ValidationError, # Make sure ValidationError is imported from zeep.exceptions
)
UNSUBSCRIBE_ERRORS = (XMLParseError, *SUBSCRIPTION_ERRORS)

TOPIC_FILTER = [
    'tns1:RuleEngine/CellMotionDetector/Motion',
    'tns1:RuleEngine/PeopleDetector/People'
]

class ONVIFMonitor:
    def __init__(self, event_handler_instance: EventHandler):
        self._ev_handler = event_handler_instance

    def broadcast_onvif_event(self, onvif_event: ONVIFEvent) -> None:
        if onvif_event.value != 'true':
            # Ignore disarm events
            return

        event = ICEEvent(
            event_id=uuid.uuid4(),
            event_name=onvif_event.event_name,
            event_source='server'
        )

        result, message = self._ev_handler.broadcast(event)

        if result == 'ignored':
            pass
        elif result == 'broadcasted':
            pass
        elif result == 'unarmed':
            pass
        else:
            pass

    async def monitor_onvif_events(self,
                                   socketio_instance: SocketIO,
                                   event_queue_instance: ICEEventQueue,
                                   onvif_ip: str,
                                   onvif_port: int,
                                   username: str,
                                   password: str):
        """Monitors ONVIF events from a camera using PullPoint subscription."""
        log.info(f'Connecting to ONVIF camera at {onvif_ip}:{onvif_port}...')
        mycam = None
        pullpoint_manager = None
        pull_messages_task = None

        try:
            mycam = ONVIFCamera(onvif_ip, onvif_port, username, password, f'{os.path.dirname(onvif.__file__)}/wsdl/', no_cache=True)
            # Ensure the device is reachable and services are initialized
            await mycam.update_xaddrs()
            log.info('Successfully connected to camera and updated XAddrs.')

            # Check if event service is available
            event_service = mycam.create_events_service()
            if not event_service:
                log.error('Event service not available on this ONVIF camera. Cannot monitor events.')
                return

            # Create PullPoint subscription
            log.info('Creating PullPoint subscription...')
            try:
                pullpoint_manager = await mycam.create_pullpoint_manager(
                    SUBSCRIPTION_TIME,
                    lambda: log.warning('ONVIF PullPoint subscription lost or expired. Events may be missed until renewed.')
                )
                await pullpoint_manager.set_synchronization_point()
                log.info('PullPoint subscription created successfully.')
            except CREATE_ERRORS as err:
                log.error(
                    f'Failed to create PullPoint subscription: {stringify_onvif_error(err)}. '
                    'Device may not support PullPoint service or has too many subscriptions.'
                )
                return

            async def _pull_messages_loop():
                """Continuously pull messages from the device."""
                while True:
                    # Monitors server up status
                    if not state.is_server_up:
                        log.info(f'Received server shutting down. Exitting ONVIF monitoring loop...')
                        pull_messages_task.cancel()
                        breakpoint

                    if pullpoint_manager is None or pullpoint_manager.closed:
                        log.info('PullPoint manager is closed, stopping message pull loop.')
                        break

                    log.debug(
                        f'Pulling PullPoint messages timeout={PULLPOINT_POLL_TIME} limit={PULLPOINT_MESSAGE_LIMIT}'
                    )
                    next_pull_delay = PULLPOINT_POLL_TIME.total_seconds() # Default delay

                    response = None
                    try:
                        response = await pullpoint_manager.get_service().PullMessages(
                            {
                                'MessageLimit': PULLPOINT_MESSAGE_LIMIT,
                                'Timeout': PULLPOINT_POLL_TIME,
                            }
                        )
                    except Fault as err:
                        log.warning(
                            f'Failed to fetch PullPoint subscription messages (Fault): {stringify_onvif_error(err)}. '
                            'Attempting to re-establish subscription.'
                        )
                        pullpoint_manager.resume()
                        next_pull_delay = SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR
                    except (
                        XMLParseError,
                        TransportError,
                        asyncio.TimeoutError,
                    ) as err:
                        log.warning(
                            f'PullPoint subscription encountered a transient error: {stringify_onvif_error(err)}. '
                            'Retrying after delay.'
                        )
                        next_pull_delay = SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR
                    except Exception as err:
                        log.error(f'An unexpected error occurred during PullMessages: {err}. Stopping monitoring.')
                        break

                    if response and (notification_messages := response.NotificationMessage):
                        for msg in notification_messages:
                            # Process every message using the generic parser
                            try:
                                # Filter events
                                topic_name = msg.Topic._value_1
                                if topic_name in TOPIC_FILTER:
                                    event = await parse_event_message(msg)
                                    if event:
                                        log.info(f'Received ONVIF Event: {event}')
                                        self.broadcast_onvif_event(socketio_instance,
                                                                   event_queue_instance,
                                                                   event)
                                    else:
                                        log.debug(f'Parser returned no event for message: {msg}')
                            except Exception as e:
                                log.error(f'Error parsing event message: {e} - Raw message: {msg}')
                    else:
                        log.debug('No new events received in this pull cycle.')

                    # Wait for the next pull cycle
                    await asyncio.sleep(next_pull_delay)

            # Start the continuous message pulling task
            pull_messages_task = asyncio.create_task(_pull_messages_loop())
            log.info('Started continuous ONVIF event pulling. Press Ctrl+C to stop.')

            await pull_messages_task

        except ONVIFError as e:
            log.error(f'ONVIF camera error: {e}')
        except Exception as e:
            log.error(f'An unexpected error occurred: {e}')
        finally:
            log.info('Stopping ONVIF event monitoring...')
            if pull_messages_task and not pull_messages_task.done():
                pull_messages_task.cancel()
                try:
                    await pull_messages_task
                except asyncio.CancelledError:
                    log.info('Event pulling task cancelled.')

            if pullpoint_manager and not pullpoint_manager.closed:
                log.info('Unsubscribing from PullPoint...')
                try:
                    await pullpoint_manager.shutdown()
                    log.info('Successfully unsubscribed from PullPoint.')
                except UNSUBSCRIBE_ERRORS as err:
                    log.warning(
                        f'Failed to unsubscribe PullPoint subscription: {stringify_onvif_error(err)}. '
                        'This is normal if the device restarted or subscription already expired.'
                    )
                except Exception as e:
                    log.error(f'Error during PullPoint shutdown: {e}')

            log.info('ONVIF event monitoring stopped.')

    async def onvif_event_monitoring_worker(self,
                                            socketio_instance: SocketIO,
                                            event_queue_instance: ICEEventQueue):

        while True:
            if not state.is_server_up:
                log.info('Shutting down onvif event monitoring worker...')
                break

            try:
                monitor_task = asyncio.create_task(self.monitor_onvif_events(
                    socketio_instance,
                    event_queue_instance,
                    CONFIG.onvif_host,
                    CONFIG.onvif_port,
                    CONFIG.onvif_username,
                    CONFIG.onvif_password
                ))
                await monitor_task
            except asyncio.CancelledError:
                log.info('ONVIF event monitoring worker was cancelled.')
                break
            except Exception as e:
                log.critical(f'Encountered critical error while monitoring ONVIF event: {e}')
                log.info('Restarting ONVIF monitoring...')