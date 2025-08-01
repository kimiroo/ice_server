import logging
from typing import Tuple

import requests
from flask_socketio import SocketIO

import utils.state as state
from utils.config import CONFIG
from utils.template_replacer import replace_values_in_dict
from objects.ice_event import ICEEvent
from objects.ice_queue import ICEEventQueue

log = logging.getLogger(__name__)

class EventHandler:
    def __init__(self,
                 socketio_instance: SocketIO,
                 event_queue_instance: ICEEventQueue):
        self._sio = socketio_instance
        self._queue = event_queue_instance

    def broadcast(self, event: ICEEvent) -> Tuple[str, str]:
        """
        Returns:
            str: Returns one of 'broadcasted', 'ignored', 'failed', 'unarmed' depending on the result
            str: Returns message if any
        """
        try:
            if not state.is_server_up:
                log.info(f'Event \'{event.name}\' ignored. (reason: ICE is disarmed)')
                return 'unarmed', None

            is_previous_event_valid = self._queue.is_previous_event_valid(event.name)
            if is_previous_event_valid:
                log.info(f'Previous event \'{event.name}\' is still valid. Ignoring this event...')
                return 'ignored', None

            # Accept event
            log.info(f'Event \'{event.name}\' accepted. Broadcasting event...')

            # Add to event queue
            self._queue.add_event(event)

            # Emit to all connected clients
            self._sio.emit('event', {
                'id': event.id,
                'name': event.name,
                'source': event.source,
                'data': event.data
            })

            # Webhooks if needed
            if CONFIG.webhook_enabled:
                request_kwargs = {}

                if isinstance(CONFIG.webhook_data, dict):
                    replaced_data = replace_values_in_dict(CONFIG.webhook_data, '$event_id', event.id)
                    replaced_data = replace_values_in_dict(replaced_data, '$event_name', event.name)
                    replaced_data = replace_values_in_dict(replaced_data, '$event_name', event.name)
                    replaced_data = replace_values_in_dict(replaced_data, '$event_source', event.source)
                    request_kwargs['json'] = replaced_data
                elif isinstance(CONFIG.webhook_data, str):
                    request_kwargs['data'] = CONFIG.webhook_data

                if isinstance(CONFIG.webhook_headers, dict):
                    request_kwargs['headers'] = CONFIG.webhook_headers

                if CONFIG.webhook_method.upper() == 'GET':
                    requests.get(CONFIG.webhook_url, **request_kwargs)
                elif CONFIG.webhook_method.upper() == 'POST':
                    requests.post(CONFIG.webhook_url, **request_kwargs)
                else:
                    log.error(f"Unsupported HTTP method: {CONFIG.webhook_method}")


        except Exception as e:
            event_name = None
            try:
                event_name = event.name
            except:
                pass
            log.error(f'Failed to handle event \'{event_name}\': {e}')
            return 'failed', str(e)