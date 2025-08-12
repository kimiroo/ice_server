import logging
import asyncio

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=logging.INFO,
    datefmt='%m/%d/%Y %I:%M:%S %p',
)

import uvicorn
import socketio

from utils.config import CONFIG
from utils.states import state
from utils.event_handler import EventHandler
from objects.event import Event
from objects.clients import Clients
from onvif_.monitor_events import ONVIFMonitor

log = logging.getLogger('main')

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*')

app = socketio.ASGIApp(sio, static_files={
    '/': 'app.html',
})

clients = Clients()
event_handler = EventHandler(sio, clients)
onvif_monitor = ONVIFMonitor(event_handler)


@sio.on('connect')
async def handle_connect(sid, environ):
    await clients.add_client(sid)
    log.info(f'Client \'{sid}\' connected.')

@sio.on('disconnect')
async def handle_disconnect(sid, reason):
    log.info(f'Client \'{sid}\' disconnected, reason: {str(reason)}')

@sio.on('introduce')
async def handle_introduce(sid, data = {}):
    log.info(f'Recieved introduce from client \'{sid}\' with data \'{data}\'.')
    event_id = data.get('id', None)
    await clients.update_client(sid, data['name'], data['type'], data.get('last_event_id', None))
    if event_id is not None:
        clients.restore_events(sid, event_id)

@sio.on('event')
async def handle_event(sid, data = {}):
    log.info(f'Recieved event from client \'{sid}\' with data \'{data}\'.')
    event_id = data.get('id', None)
    event_event = data.get('event', None)
    event_type = data.get('type', None)
    event_source = data.get('source', None)
    event_data = data.get('data', None)

    if event_id is None or event_event is None or event_type is None or event_source is None:
        await sio.emit('event_result', {
            'id': event_id,
            'result': 'failed',
            'reason': 'invalid_scheme'
        }, to=sid)
        return

    event = Event(event_id, event_event, event_type, event_source, event_data)
    result, broadcast_type = await event_handler.broadcast(event)

    payload = {
        'id': event_id,
        'result': result
    }

    if result != 'success':
        payload['reason'] = broadcast_type

    await sio.emit('event_result', payload, to=sid)

@sio.on('set_armed')
async def handle_set_armed(sid, data = {}):
    log.info(f'Recieved set_armed from client \'{sid}\' with data \'{data}\'.')
    state.set_armed(data.get('armed', False))

@sio.on('get')
async def handle_get(sid, data = {}):
    log.debug(f'Recieved get from client \'{sid}\' with data \'{data}\'.')
    payload = {
        'isArmed': state.is_armed(),
        'clientList': await clients.get_client_list(True),
        'eventList': await clients.get_event_list(sid, True)
    }
    await sio.emit('get_result', payload)

@sio.on('ack')
async def handle_ack(sid, data = {}):
    log.debug(f'Recieved ack from client \'{sid}\' with data \'{data}\'.')
    event_id = data.get('id', None)
    await clients.ack_event(sid, event_id)
    await clients.update_last_seen(sid)

@sio.on('pong')
async def handle_pong(sid, data = {}):
    log.debug(f'Recieved pong from client \'{sid}\' with data \'{data}\'.')
    await clients.update_last_seen(sid)

async def ping_worker():
    while state.is_server_up():
        await sio.emit('ping')
        await asyncio.sleep(.1)

async def client_worker():
    while state.is_server_up():
        deleted_client_sids = await clients.clean_client()
        for sid in deleted_client_sids:
            await sio.disconnect(sid)
        await asyncio.sleep(.1)

async def event_worker():
    while state.is_server_up():
        await clients.clean_event()
        await asyncio.sleep(.1)

async def main():
    try:
        log.info(f'Starting background workers...')
        asyncio.create_task(ping_worker())
        asyncio.create_task(client_worker())
        asyncio.create_task(event_worker())
        if CONFIG.onvif_enabled:
            asyncio.create_task(onvif_monitor.onvif_event_monitoring_worker())

        log.info(f'Listening at http://{CONFIG.host}:{CONFIG.port}...')
        uvicorn_config = uvicorn.Config(app,
                                        host=CONFIG.host,
                                        port=CONFIG.port,
                                        log_config='./utils/uvicorn_log_config.yaml')
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()
    except [KeyboardInterrupt, asyncio.exceptions.CancelledError]:
        pass
    except Exception as e:
        log.error(f'Unexpected error occured: {e}')
    finally:
        log.info('Shutting down...')
        state.set_server_up(False)
        await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())