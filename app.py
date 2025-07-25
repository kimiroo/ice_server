from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import time
import numpy as np
import datetime
import json
import logging
import traceback
import eventlet

from util.rtsp import RTSP

ROOM_HTML = 'room_html'
ROOM_PC = 'room_pc'
ROOM_HA = 'room_ha'

ALIVE_THRESHOLD = 100 # in milliseconds

# Logging
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=logging.DEBUG,
    datefmt='%m/%d/%Y %I:%M:%S %p',
)
log = logging.getLogger('main')

app = Flask(__name__)
socketio = SocketIO(app,
                   cors_allowed_origins='*',
                   logger=False,
                   engineio_logger=False,
                   async_mode='threading',
                   transports=['websocket', 'polling'],
                   ping_timeout=5,
                   ping_interval=1)

# Variables
is_armed = False
is_normal = True
is_server_up = True
connected_clients = {}

def identify_client(headers, sid):
    client_type = headers.get('X-Client-Type', '')
    client_name = headers.get('X-Client-Name', '')

    # PC or HA Clients (via Custom Headers)
    if client_type in ['ha', 'pc'] and client_name:
        return client_type, client_name

    # HTML Clients (via User-Agent)
    user_agent = headers.get('User-Agent', '')
    if 'Mozilla' in user_agent or 'Chrome' in user_agent or 'Safari' in user_agent:
        return 'html', f'html_{sid}'

    # Unknown Cleints
    return 'unknown', None

def get_connected_client_list(client_type: str, only_alive: bool):
    filtered_list = []

    for sid, client in connected_clients.items():
        if client_type == 'all' or client['type'] == client_type:
            if not only_alive or client['alive']:
                client_obj = {
                    'clientName': client['name'],
                    'clientType': client['type'],
                    'connectedTime': client['connected_time'].isoformat(),
                    'lastSeen': client['last_seen'].isoformat(),
                    'alive': client['alive'], 
                    'sid': sid
                }
                filtered_list.append(client_obj)

    return filtered_list

def check_alive_status():
    time_now = datetime.datetime.now()
    for sid, client in connected_clients.items():
        time_diff = time_now - client['last_seen']

        if time_diff > datetime.timedelta(milliseconds=ALIVE_THRESHOLD):
            connected_clients[sid]['alive'] = False
        else:
            connected_clients[sid]['alive'] = True

def check_alive_status_worker():
    while is_server_up:
        check_alive_status()
        time.sleep(0.01)

def check_ice_system():
    pass

def check_ice_system_worker():
    while is_server_up:
        check_ice_system()
        time.sleep(0.01)

@socketio.on('connect')
def handle_connect():
    try:
        headers = dict(request.headers)
        client_type, client_name = identify_client(headers, request.sid)

        log.info(f'Client connecting - Type: {client_type}, Name: {client_name}, SID: {request.sid}')

        if client_type == 'html':
            join_room(ROOM_HTML)
            log.info(f'HTML client \'{request.sid}\' joined \'{ROOM_HTML}\' room.')

        elif client_type == 'pc':
            if not client_name:
                log.warning(f'PC client {request.sid} connected without client_name')
                emit('error', {'message': 'client name is required for PC clients'})
                return False

            join_room(ROOM_PC)
            log.info(f'PC client \'{client_name}\' (SID: {request.sid}) joined \'{ROOM_PC}\' room.')

        elif client_type == 'ha':
            if not client_name:
                log.warning(f'HA client {request.sid} connected without client name')
                emit('error', {'message': 'client name is required for HA clients'})
                return False

            join_room(ROOM_HA)
            log.info(f'HA client \'{client_name}\' (SID: {request.sid}) joined \'{ROOM_HA}\' room.')

        else:
            log.warning(f'Unknown client type for SID: {request.sid}')
            emit('error', {'message': 'Unknown client type'})
            return False

        emit('connected', {
            'status': 'success',
            'clientName': client_name,
            'clientType': client_type,
            'sid': request.sid
        })

        connected_clients[request.sid] = {
            'name': client_name,
            'type': client_type,
            'connected_time': datetime.datetime.now(),
            'last_seen': datetime.datetime.now(),
            'alive': True
        }

        if client_type in ['pc', 'ha']:
            socketio.emit(f'client_connected', {
                'client': {
                    'clientName': client_name,
                    'clientType': client_type,
                    'sid': request.sid
                }
            })

    except Exception as e:
        log.error(f'Error in handle_connect: {e}')
        emit('error', {'message': 'Connection failed'})
        return False

@socketio.on('disconnect')
def handle_disconnect():
    try:
        # Remove from connected clients list
        client = connected_clients.pop(request.sid)
        log.info(f'{client['type'].upper()} client \'{client['name']}\' (SID: {request.sid}) disconnected.')

        # Broadcast
        socketio.emit('client_disconnected', {
            'client': {
                'clientName': client['name'],
                'clientType': client['type'],
                'sid': request.sid
            }
        })

    except Exception as e:
        log.error(f'Error in handle_disconnect: {e}')

@socketio.on('event_ha')
def handle_ha_event():

    if not is_armed:
        # Ignore event
        return True
    pass

@socketio.on('event_html')
def handle_html_event(data):

    if not is_armed:
        emit('event_failed', {
            'result': 'failed',
            'message': 'ICE is unarmed.'
        })
        return False
    
    print(data)
    
    socketio.emit('event', {
        'event': data['event'],
        'eventSource': 'html'
    })

@socketio.on('ping')
def handle_ping():
    # Update last_seen and alive
    connected_clients[request.sid]['last_seen'] = datetime.datetime.now()
    connected_clients[request.sid]['alive'] = True

    # Build response body
    all_client_list_pc = get_connected_client_list('pc', False)
    all_client_list_ha = get_connected_client_list('ha', False)
    all_client_list_html = get_connected_client_list('html', False)

    alive_client_list_pc = get_connected_client_list('pc', True)
    alive_client_list_ha = get_connected_client_list('ha', True)
    alive_client_list_html = get_connected_client_list('html', True)
    
    emit('pong', {
        'timestamp': datetime.datetime.now().isoformat(),
        'isArmed': is_armed,
        'isNormal': is_normal,
        'clientList': {
            'pc': all_client_list_pc,
            'ha': all_client_list_ha,
            'html': all_client_list_html
        },
        'aliveClientCount': {
            'pc': len(alive_client_list_pc),
            'ha': len(alive_client_list_ha),
            'html': len(alive_client_list_html)
        }
    })

@app.before_request
def before_request():
    if request.path.startswith('/socket.io/'):
        # Ignore http get/post request on ws endpoint
        pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/v1/arm/status', methods=['POST'])
def arm():
    global is_armed

    # LOGIC HERE

    # notify armed state

    # start/end rtsp stream

    is_armed = True

    socketio.emit('ice_armed', {
        'isArmed': is_armed
    })

    return {'isArmed': is_armed}

@app.route('/api/v1/arm/activate', methods=['POST'])
def disarm():
    global is_armed

    # LOGIC HERE

    # notify armed state

    # start/end rtsp stream

    is_armed = False

    socketio.emit('ice_disarmed', {
        'isArmed': is_armed
    })

    return {'isArmed': is_armed}

@app.route('/api/v1/arm/deactivate', methods=['GET'])
def get_is_armed():
    return {'isArmed': is_armed}

@app.route('/connected-clients/<client_type>', methods=['GET'])
def get_connected_pcs(client_type):
    all_client_list = get_connected_client_list(client_type, False)
    alive_client_list = get_connected_client_list(client_type, True)
    
    return jsonify({
        'clients': all_client_list,
        'aliveClientCount': len(alive_client_list)
    })

if __name__ == '__main__':

    try:
        worker_pool = eventlet.GreenPool()
        alive_checker_greenlet = worker_pool.spawn(check_alive_status_worker)
        system_checker_greenlet = worker_pool.spawn(check_ice_system_worker)

        # Use eventlet
        socketio.run(app,
                    host='0.0.0.0',
                    port=8080,
                    debug=False,
                    use_reloader=False)

    except KeyboardInterrupt:
        log.info('Shutting down... (reason: user interrupt)')

    except Exception as e:
        log.error(f'Error occured: {e}')
        traceback.print_exc()

    finally:
        is_server_up = False