from __future__ import annotations

import os
import asyncio
import datetime as dt
import logging
from typing import Any

import onvif
from onvif import ONVIFCamera
from onvif.client import PullPointManager as ONVIFPullPointManager, retry_connection_error
from onvif.exceptions import ONVIFError
from onvif.util import stringify_onvif_error
from zeep.exceptions import Fault, TransportError, XMLParseError
from zeep.exceptions import ValidationError # Ensure this is imported for CREATE_ERRORS
from onvif_parser import parse_event_message

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

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

async def monitor_onvif_events(
    camera_ip: str,
    camera_port: int,
    username: str,
    password: str,
):
    """Monitors ONVIF events from a camera using PullPoint subscription."""
    LOGGER.info(f"Connecting to ONVIF camera at {camera_ip}:{camera_port}...")
    mycam = None
    pullpoint_manager = None
    pull_messages_task = None

    try:
        mycam = ONVIFCamera(camera_ip, camera_port, username, password, f"{os.path.dirname(onvif.__file__)}/wsdl/", no_cache=True)
        # Ensure the device is reachable and services are initialized
        await mycam.update_xaddrs()
        LOGGER.info("Successfully connected to camera and updated XAddrs.")

        # Check if event service is available
        event_service = mycam.create_events_service()
        if not event_service:
            LOGGER.error("Event service not available on this ONVIF camera. Cannot monitor events.")
            return

        # Create PullPoint subscription
        LOGGER.info("Creating PullPoint subscription...")
        try:
            pullpoint_manager = await mycam.create_pullpoint_manager(
                SUBSCRIPTION_TIME,
                lambda: LOGGER.warning("ONVIF PullPoint subscription lost or expired. Events may be missed until renewed.")
            )
            await pullpoint_manager.set_synchronization_point()
            LOGGER.info("PullPoint subscription created successfully.")
        except CREATE_ERRORS as err:
            LOGGER.error(
                f"Failed to create PullPoint subscription: {stringify_onvif_error(err)}. "
                "Device may not support PullPoint service or has too many subscriptions."
            )
            return

        async def _pull_messages_loop():
            """Continuously pull messages from the device."""
            while True:
                if pullpoint_manager is None or pullpoint_manager.closed:
                    LOGGER.info("PullPoint manager is closed, stopping message pull loop.")
                    break

                LOGGER.debug(
                    f"Pulling PullPoint messages timeout={PULLPOINT_POLL_TIME} limit={PULLPOINT_MESSAGE_LIMIT}"
                )
                next_pull_delay = PULLPOINT_POLL_TIME.total_seconds() # Default delay

                response = None
                try:
                    response = await pullpoint_manager.get_service().PullMessages(
                        {
                            "MessageLimit": PULLPOINT_MESSAGE_LIMIT,
                            "Timeout": PULLPOINT_POLL_TIME,
                        }
                    )
                except Fault as err:
                    LOGGER.warning(
                        f"Failed to fetch PullPoint subscription messages (Fault): {stringify_onvif_error(err)}. "
                        "Attempting to re-establish subscription."
                    )
                    pullpoint_manager.resume()
                    next_pull_delay = SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR
                except (
                    XMLParseError,
                    TransportError,
                    asyncio.TimeoutError,
                ) as err:
                    LOGGER.warning(
                        f"PullPoint subscription encountered a transient error: {stringify_onvif_error(err)}. "
                        "Retrying after delay."
                    )
                    next_pull_delay = SUBSCRIPTION_RESTART_INTERVAL_ON_ERROR
                except Exception as err:
                    LOGGER.error(f"An unexpected error occurred during PullMessages: {err}. Stopping monitoring.")
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
                                    LOGGER.info(f"Received ONVIF Event: {event}")
                                else:
                                    LOGGER.debug(f"Parser returned no event for message: {msg}")
                        except Exception as e:
                            LOGGER.error(f"Error parsing event message: {e} - Raw message: {msg}")
                else:
                    LOGGER.debug("No new events received in this pull cycle.")

                # Wait for the next pull cycle
                await asyncio.sleep(next_pull_delay)

        # Start the continuous message pulling task
        pull_messages_task = asyncio.create_task(_pull_messages_loop())
        LOGGER.info("Started continuous ONVIF event pulling. Press Ctrl+C to stop.")

        await pull_messages_task

    except ONVIFError as e:
        LOGGER.error(f"ONVIF camera error: {e}")
    except Exception as e:
        LOGGER.error(f"An unexpected error occurred: {e}")
    finally:
        LOGGER.info("Stopping ONVIF event monitoring...")
        if pull_messages_task and not pull_messages_task.done():
            pull_messages_task.cancel()
            try:
                await pull_messages_task
            except asyncio.CancelledError:
                LOGGER.info("Event pulling task cancelled.")

        if pullpoint_manager and not pullpoint_manager.closed:
            LOGGER.info("Unsubscribing from PullPoint...")
            try:
                await pullpoint_manager.shutdown()
                LOGGER.info("Successfully unsubscribed from PullPoint.")
            except UNSUBSCRIBE_ERRORS as err:
                LOGGER.warning(
                    f"Failed to unsubscribe PullPoint subscription: {stringify_onvif_error(err)}. "
                    "This is normal if the device restarted or subscription already expired."
                )
            except Exception as e:
                LOGGER.error(f"Error during PullPoint shutdown: {e}")

        LOGGER.info("ONVIF event monitoring stopped.")

async def main():
    # --- Configure your ONVIF camera details here ---
    CAMERA_IP = '10.5.21.10'
    CAMERA_PORT = 2020
    CAMERA_USERNAME = 'tapo_cam'
    CAMERA_PASSWORD = 'password'

    try:
        while True:
            monitor_task = asyncio.create_task(monitor_onvif_events(
                CAMERA_IP, CAMERA_PORT, CAMERA_USERNAME, CAMERA_PASSWORD
            ))
            await monitor_task
    except KeyboardInterrupt:
        LOGGER.info("Monitoring interrupted by user (Ctrl+C).")
    except Exception as e:
        LOGGER.critical(f"Script terminated due to unhandled error: {e}")

if __name__ == "__main__":
    asyncio.run(main())