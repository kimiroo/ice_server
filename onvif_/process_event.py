import uuid
import queue
import logging
import traceback

import utils.state as state
from utils.event_handler import EventHandler
from objects.ice_event import ICEEvent
from onvif_.event_parser import ONVIFEvent

log = logging.getLogger(__name__)

class ONVIFEventProcessor:
    def __init__(self,
                 queue: queue.Queue,
                 event_handler_instance: EventHandler):

        self._queue = queue
        self._ev_handler = event_handler_instance

    def monitor_onvif_event_queue(self) -> None:
        """
        Broadcasts an ONVIF event using the internal event handler.
        Ignores 'disarm' events.
        """
        while state.is_server_up:
            try:
                event: ONVIFEvent = self._queue.get()

                if event.value != True:
                    # Ignore disarm events
                    continue

                event = ICEEvent(
                    event_id=uuid.uuid4(),
                    event_name=event.event_name,
                    event_source='server'
                )

                result, message = self._ev_handler.broadcast(event)

            except Exception as e:
                print(e)
                traceback.print_exc()