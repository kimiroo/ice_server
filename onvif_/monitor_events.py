from __future__ import annotations

import os
import uuid
import time
import datetime as dt
import logging

import onvif
from zeep.exceptions import Fault, TransportError, XMLParseError, ValidationError
from onvif.client import ONVIFCamera
from onvif.exceptions import ONVIFError

import utils.state as state
from utils.config import CONFIG
from utils.event_handler import EventHandler
from objects.ice_event import ICEEvent
from objects.ice_queue import ICEEventQueue
from onvif_.event_parser import ONVIFEvent, parse_event_message

log = logging.getLogger(__name__)

# Constants for subscription management
SUBSCRIPTION_TIME = dt.timedelta(minutes=10)
PULLPOINT_POLL_TIME = dt.timedelta(seconds=1)  # How long to wait for messages in one pull request
PULLPOINT_MESSAGE_LIMIT = 100  # Max messages to pull at once
SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR = 1  # Seconds to wait before retrying on error

# ONVIF Error types
SUBSCRIPTION_ERRORS = (Fault, TimeoutError, TransportError)
CREATE_ERRORS = (
    ONVIFError,
    Fault,
    TimeoutError,
    XMLParseError,
    ValidationError,
)
UNSUBSCRIBE_ERRORS = (XMLParseError, *SUBSCRIPTION_ERRORS)

TOPIC_FILTER = [
    'tns1:RuleEngine/CellMotionDetector/Motion',
    'tns1:RuleEngine/PeopleDetector/People'
]

class ONVIFMonitor:
    def __init__(self, event_handler_instance: EventHandler):
        """Initializes the ONVIFMonitor with an event handler."""
        self._ev_handler = event_handler_instance

    def broadcast_onvif_event(self, onvif_event: ONVIFEvent) -> None:
        """
        Broadcasts an ONVIF event using the internal event handler.
        Ignores 'disarm' events.
        """
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
            log.debug(f'Event ignored: {message}')
        elif result == 'broadcasted':
            log.info(f'Event broadcasted: {message}')
        elif result == 'unarmed':
            log.warning(f'Event was not broadcasted because the system is unarmed: {message}')
        else:
            log.error(f'Unknown result from event broadcast: {result} - {message}')

    def monitor_onvif_events(self,
                             onvif_ip: str,
                             onvif_port: int,
                             username: str,
                             password: str):
        """Monitors ONVIF events from a camera using PullPoint subscription."""
        log.info(f'Connecting to ONVIF camera at {onvif_ip}:{onvif_port}...')
        mycam = None
        pullpoint_manager = None

        try:
            # The ONVIFCamera constructor is now synchronous.
            mycam = ONVIFCamera(onvif_ip, onvif_port, username, password, f'{os.path.dirname(onvif.__file__)}/wsdl/', no_cache=True)
            # The update_xaddrs method is also synchronous.
            mycam.update_xaddrs()
            log.info('Successfully connected to camera and updated XAddrs.')

            # Check if event service is available
            event_service = mycam.create_events_service()
            if not event_service:
                log.error('Event service not available on this ONVIF camera. Cannot monitor events.')
                return

            # Create PullPoint subscription synchronously
            log.info('Creating PullPoint subscription...')
            try:
                # The create_pullpoint_manager method is now synchronous.
                pullpoint_manager = mycam.create_pullpoint_manager(
                    SUBSCRIPTION_TIME,
                    lambda: log.warning('ONVIF PullPoint subscription lost or expired. Events may be missed until renewed.')
                )
                pullpoint_manager.set_synchronization_point()
                log.info('PullPoint subscription created successfully.')
            except CREATE_ERRORS as err:
                log.error(
                    f'Failed to create PullPoint subscription: {str(err)}. '
                    'Device may not support PullPoint service or has too many subscriptions.'
                )
                return

            # This is the synchronous equivalent of the async loop
            while state.is_server_up:
                if pullpoint_manager is None or pullpoint_manager.closed:
                    log.info('PullPoint manager is closed, stopping message pull loop.')
                    break

                log.debug(
                    f'Pulling PullPoint messages timeout={PULLPOINT_POLL_TIME} limit={PULLPOINT_MESSAGE_LIMIT}'
                )
                next_pull_delay = PULLPOINT_POLL_TIME.total_seconds()  # Default delay

                response = None
                try:
                    # Synchronous call to PullMessages
                    response = pullpoint_manager.get_service().PullMessages(
                        {
                            'MessageLimit': PULLPOINT_MESSAGE_LIMIT,
                            'Timeout': PULLPOINT_POLL_TIME,
                        }
                    )
                except Fault as err:
                    log.warning(
                        f'Failed to fetch PullPoint subscription messages (Fault): {str(err)}. '
                        'Attempting to re-establish subscription.'
                    )
                    pullpoint_manager.resume()
                    next_pull_delay = SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR
                except (
                    XMLParseError,
                    TransportError,
                    TimeoutError,
                ) as err:
                    log.warning(
                        f'PullPoint subscription encountered a transient error: {str(err)}. '
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
                                # The parse_event_message function is assumed to be synchronous or refactored.
                                event = parse_event_message(msg)
                                if event:
                                    log.info(f'Received ONVIF Event: {event}')
                                    self.broadcast_onvif_event(event)
                                else:
                                    log.debug(f'Parser returned no event for message: {msg}')
                        except Exception as e:
                            log.error(f'Error parsing event message: {e} - Raw message: {msg}')
                else:
                    log.debug('No new events received in this pull cycle.')

                # Wait for the next pull cycle synchronously
                time.sleep(next_pull_delay)

        except ONVIFError as e:
            log.error(f'ONVIF camera error: {e}')
        except Exception as e:
            log.error(f'An unexpected error occurred: {e}')
        finally:
            log.info('Stopping ONVIF event monitoring...')
            if pullpoint_manager and not pullpoint_manager.closed:
                log.info('Unsubscribing from PullPoint...')
                try:
                    # Synchronous shutdown call
                    pullpoint_manager.shutdown()
                    log.info('Successfully unsubscribed from PullPoint.')
                except UNSUBSCRIBE_ERRORS as err:
                    log.warning(
                        f'Failed to unsubscribe PullPoint subscription: {str(err)}. '
                        'This is normal if the device restarted or subscription already expired.'
                    )
                except Exception as e:
                    log.error(f'Error during PullPoint shutdown: {e}')

            log.info('ONVIF event monitoring stopped.')

    def onvif_event_monitoring_worker(self,
                                      socketio_instance: any,
                                      event_queue_instance: any):
        """
        Synchronous worker that continuously attempts to start ONVIF event monitoring.
        Restarts if the monitoring loop fails unexpectedly.
        """
        while state.is_server_up:
            try:
                # Direct synchronous function call
                self.monitor_onvif_events(
                    CONFIG.onvif_host,
                    CONFIG.onvif_port,
                    CONFIG.onvif_username,
                    CONFIG.onvif_password
                )
            except Exception as e:
                log.critical(f'Encountered critical error while monitoring ONVIF event: {e}')
                log.info('Restarting ONVIF monitoring...')

            # Add a small delay before restarting the monitoring loop to prevent a tight loop
            if not state.is_server_up:
                log.info('Shutting down onvif event monitoring worker...')
                break

            time.sleep(1) # Small delay before retrying

        log.info('Shutting down onvif event monitoring worker...')
