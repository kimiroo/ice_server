from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import time
import numpy as np
from datetime import datetime
import json
import logging

from util.rtsp import RTSP

ROOM_HTML = 'room_html'
ROOM_PC = 'room_pc'
ROOM_HA = 'room_ha'

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

def get_connected_client_list(client_type: str):
    return [
        {
            'clientName': info['name'],
            'clientType': info['type'],
            'connectedTime': info['connected_time'].isoformat(),
            'sid': sid
        }
        for sid, info in connected_clients.items()
        if client_type == 'all' or info.get('type') == client_type
    ]

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
            'connected_time': datetime.now()
        }

        if client_type in ['pc', 'ha']:
            socketio.emit(f'client_connected', {
                'client': {
                    'clientName': client_name,
                    'clientType': client_type,
                    'sid': request.sid
                },
                'clientList': {
                    'pc': get_connected_client_list('pc'),
                    'ha': get_connected_client_list('ha')
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
            },
            'clientList': {
                'pc': get_connected_client_list('pc'),
                'ha': get_connected_client_list('ha')
            }
        })

    except Exception as e:
        log.error(f'Error in handle_disconnect: {e}')

@app.before_request
def before_request():
    if request.path.startswith('/socket.io/'):
        # Socket.IO 핸드셰이크를 위한 특별 처리
        pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/arm', methods=['POST'])
def arm():
    global is_armed

    # LOGIC HERE

    is_armed = True

@app.route('/disarm', methods=['POST'])
def disarm():
    global is_armed

    # LOGIC HERE

    is_armed = False

@app.route('/is-armed', methods=['GET'])
def get_is_armed():
    return {'isArmed': is_armed}

@app.route('/connected-clients/<client_type>', methods=['GET'])
def get_connected_pcs(client_type):
    clients = get_connected_client_list(client_type)
    return jsonify({
        'clients': clients,
        'count': len(clients)
    })

if __name__ == '__main__':

    # eventlet 사용으로 변경
    socketio.run(app,
                host='0.0.0.0',
                port=8080,
                debug=False,
                use_reloader=True)  # 디버그 모드에서 reloader 비활성화