from typing import Tuple, TYPE_CHECKING

import logging
import asyncio
import socketio

import aiohttp

from utils.config import CONFIG
from utils.states import state
from utils.template_replacer import recursive_replace

if TYPE_CHECKING:
    from objects.event import Event
    from objects.clients import Clients

VALIDITY_CHECK_TARGET_EVENT_NAMES = [
    # Empty at the moment
]
VALIDITY_CHECK_TARGET_EVENT_TYPES = [
    'onvif'
]

log = logging.getLogger(__name__)

class EventHandler:
    def __init__(self,
                 socketio_instance: socketio.AsyncServer,
                 clients_instance: 'Clients'):
        self._sio = socketio_instance
        self._clients = clients_instance

    async def call_webhook(self, event: 'Event') -> None:
        request_kwargs = {}

        replacements_map = {
            '$event_id': str(event.id),
            '$event_name': event.event,
            '$event_type': event.type,
            '$event_source': event.source,
            '$event_data': event.data,
            '$event_timestamp': event.timestamp.isoformat()
        }
        replaced_data = recursive_replace(CONFIG.webhook_data, replacements_map)

        # Append data
        if isinstance(CONFIG.webhook_data, dict):
            request_kwargs['json'] = replaced_data
        elif isinstance(CONFIG.webhook_data, str):
            request_kwargs['data'] = replaced_data

        # Append headers
        if isinstance(CONFIG.webhook_headers, dict):
            request_kwargs['headers'] = CONFIG.webhook_headers

        # Call webhook
        try:
            async with aiohttp.ClientSession() as session:
                method = CONFIG.webhook_method.upper()
                url = CONFIG.webhook_url

                if method == 'GET':
                    log.info(f'Firing GET webhook to {url}...')
                    async with session.get(url, **request_kwargs) as response:
                        log.debug(f"Webhook response status: {response.status}")
                elif method == 'POST':
                    log.info(f'Firing POST webhook to {url}...')
                    async with session.post(url, **request_kwargs) as response:
                        log.debug(f"Webhook response status: {response.status}")
                else:
                    log.error(f"Unsupported HTTP method: {CONFIG.webhook_method}")
        except aiohttp.ClientError as e:
            log.error(f"Webhook call failed: {e}")

    async def broadcast(self, event: 'Event') -> Tuple[str, str]:
        is_previous_event_valid = await self._clients.is_previous_event_valid(event.event)
        broadcast_type = 'event_ignored'
        result = ''
        payload = {
            'event': event.to_dict(json_friendly=True)
        }
        if (is_previous_event_valid and
            ((event.event in VALIDITY_CHECK_TARGET_EVENT_NAMES) or
             (event.type in VALIDITY_CHECK_TARGET_EVENT_TYPES))):
            log.debug(f'Event \'{event.event}\' ignored. (reason: Previous event still valid)')
            payload['reason'] = 'previous_valid'
            result = 'ignored'
        else:
            if state.is_armed():
                log.info(f'Event \'{event.event}\' accepted. Broadcasting event...')
                broadcast_type = 'event'
                result = 'success'
                await self._clients.add_event(event)
            else:
                log.debug(f'Event \'{event.event}\' ignored. (reason: ICE is disarmed)')
                payload['reason'] = 'not_armed'
                result = 'ignored'


        await self._sio.emit(broadcast_type, payload)

        # Call webhook if enabled
        if CONFIG.webhook_enabled and (broadcast_type == 'event' or CONFIG.webhook_on_ignored):
            if len(CONFIG.webhook_on_event_type) > 0 and event.type not in CONFIG.webhook_on_event_type:
                return result, broadcast_type
            if len(CONFIG.webhook_on_event_source) > 0 and event.source not in CONFIG.webhook_on_event_source:
                return result, broadcast_type

            asyncio.create_task(self.call_webhook(event))

        return result, broadcast_type
