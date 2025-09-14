import os
import logging

DEFAULT_LOG_LEVEL = 'INFO'

log_level = os.environ.get('LOG_LEVEL', DEFAULT_LOG_LEVEL).upper()

if log_level not in logging._nameToLevel:
    log_level = DEFAULT_LOG_LEVEL

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=log_level,
    datefmt='%Y-%m-%d %H:%M:%S',
)

import os
import uuid
import asyncio
import uvicorn
import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from utils.config import CONFIG
from utils.states import state
from utils.event_handler import EventHandler
from objects.event import Event
from objects.client import Client
from objects.clients import Clients
from onvif_.monitor_events import ONVIFMonitor

log = logging.getLogger('main')

HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '28080'))

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*')

app = FastAPI()
clients = Clients()
event_handler = EventHandler(sio, clients)
onvif_monitor = ONVIFMonitor(event_handler)


@app.get('/api/v1/go2rtc-config')
async def get_go2rtc_config():
    payload = {
        'host': CONFIG.go2rtc_host,
        'src': CONFIG.go2rtc_src
    }
    return payload

@app.get('/api/v1/health')
async def get_health():
    return 'I\'m healthy!'

app.mount('/socket.io', socketio.ASGIApp(sio, other_asgi_app=app))
app.mount('/', StaticFiles(directory='static', html=True), name='static')

@sio.on('connect')
async def handle_connect(sid, environ):
    await clients.add_client(sid)
    log.info(f'Client \'{sid}\' connected.')

@sio.on('disconnect')
async def handle_disconnect(sid, reason):
    client: Client = await clients.get_client(sid)
    log.info(f'Client \'{sid}\' ({client.name}, {client.type}) disconnected, reason: {str(reason)}')
    event = Event(
        event_id=uuid.uuid4(),
        event_event='disconnected',
        event_type='client',
        event_source='server',
        event_data={'client': client.to_dict(json_friendly=True)}
    )
    await event_handler.broadcast(event)
    await clients.remove_client(sid)

@sio.on('introduce')
async def handle_introduce(sid, data = {}):
    log.info(f'Recieved introduce from client \'{sid}\' with data \'{data}\'.')
    client_name = data.get('name', None)
    client_type = data.get('type', None)
    last_event_id = data.get('lastEventID', None)

    await clients.update_client(sid, client_name, client_type, last_event_id)
    client: Client = await clients.get_client(sid)
    event = Event(
        event_id=uuid.uuid4(),
        event_event='connected',
        event_type='client',
        event_source='server',
        event_data={'client': client.to_dict(json_friendly=True)}
    )
    await event_handler.broadcast(event)

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
        try:
            await sio.emit('ping')
            await asyncio.sleep(.1)
        except asyncio.CancelledError:
            log.info('Ping worker was cancelled.')
            break
        except Exception:
            pass

async def client_worker():
    while state.is_server_up():
        try:
            deleted_client_sids = await clients.clean_client()
            for sid in deleted_client_sids:
                await sio.disconnect(sid)
            await asyncio.sleep(.1)
        except asyncio.CancelledError:
            log.info('Client cleaner worker was cancelled.')
            break
        except Exception:
            pass

async def event_worker():
    while state.is_server_up():
        try:
            await clients.clean_event()
            await asyncio.sleep(.1)
        except asyncio.CancelledError:
            log.info('Event cleaner worker was cancelled.')
            break
        except Exception:
            pass

async def main():
    while True:
        try:
            log.info(f'Starting background workers...')
            task_ping_worker = asyncio.create_task(ping_worker())
            task_client_worker = asyncio.create_task(client_worker())
            task_event_worker = asyncio.create_task(event_worker())
            if CONFIG.onvif_enabled:
                asyncio.create_task(onvif_monitor.onvif_event_monitoring_worker())

            log.info(f'Listening at http://{CONFIG.host}:{CONFIG.port}...')
            uvicorn_config = uvicorn.Config(app,
                                            host=HOST,
                                            port=PORT,
                                            log_config=None,
                                            log_level=None,
                                            access_log=False)
            uvicorn_server = uvicorn.Server(uvicorn_config)
            await uvicorn_server.serve()
        except [KeyboardInterrupt, asyncio.exceptions.CancelledError]:
            pass
        except Exception as e:
            log.error(f'Unexpected error occured: {e}')
        finally:
            log.info('Shutting down...')
            state.set_server_up(False)
            task_ping_worker.cancel()
            task_client_worker.cancel()
            task_event_worker.cancel()
            await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())