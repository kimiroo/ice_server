from __future__ import annotations

import os
import asyncio
import datetime
import logging
import queue
import traceback

from flask_socketio import SocketIO

import onvif
from onvif import ONVIFCamera
from onvif.exceptions import ONVIFError
from onvif.util import stringify_onvif_error
from zeep.exceptions import Fault, TransportError, XMLParseError
from zeep.exceptions import ValidationError # Ensure this is imported for CREATE_ERRORS

import utils.state as state
from utils.config import CONFIG
from onvif_.event_parser import parse_event_message

log = logging.getLogger(__name__)

# Constants for subscription management
SUBSCRIPTION_TIME = datetime.timedelta(minutes=10)
PULLPOINT_POLL_TIME = datetime.timedelta(seconds=1) # How long to wait for messages in one pull request
PULLPOINT_MESSAGE_LIMIT = 100 # Max messages to pull at once

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
    def __init__(self, queue: queue.Queue):
        self._queue = queue

    async def monitor_onvif_events(self,
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
                        traceback.print_exc()
                        pullpoint_manager.resume()
                    except (
                        XMLParseError,
                        TransportError,
                        asyncio.TimeoutError,
                    ) as err:
                        log.warning(
                            f'PullPoint subscription encountered a transient error: {stringify_onvif_error(err)}. '
                            'Retrying after delay.'
                        )
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
                                        log.debug(f'Received ONVIF Event: {event}')
                                        self._queue.put(event)
                                    else:
                                        log.debug(f'Parser returned no event for message: {msg}')
                            except Exception as e:
                                log.error(f'Error parsing event message: {e} - Raw message: {msg}')
                    else:
                        log.debug('No new events received in this pull cycle.')

                    # Wait for the next pull cycle
                    await asyncio.sleep(PULLPOINT_POLL_TIME.total_seconds())

            # Start the continuous message pulling task
            pull_messages_task = asyncio.create_task(_pull_messages_loop())
            log.info('Started continuous ONVIF event pulling.')

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

    def onvif_event_monitoring_worker(self):

        while state.is_server_up:
            try:
                asyncio.run(self.monitor_onvif_events(
                    CONFIG.onvif_host,
                    CONFIG.onvif_port,
                    CONFIG.onvif_username,
                    CONFIG.onvif_password
                ))
            except asyncio.CancelledError:
                log.info('ONVIF event monitoring worker was cancelled.')
                break
            except Exception as e:
                log.critical(f'Encountered critical error while monitoring ONVIF event: {e}')
                log.info('Restarting ONVIF monitoring...')

        log.info('Shutting down onvif event monitoring worker...')