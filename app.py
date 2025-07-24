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
ROOM_HEADLESS = 'room_headless'

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
                   async_mode='threading')

# Variables
is_armed = False

@socketio.on('connect')
def handle_connect():
    if 'Mozilla' in request.headers.get('User-Agent', ''):
        join_room(ROOM_HTML)
        print(f'Client \'{request.sid}\' joined \'{ROOM_HTML}\' room.')

    else:
        join_room(ROOM_HEADLESS)
        print(f'Client \'{request.sid}\' joined \'{ROOM_HEADLESS}\' room.')

@socketio.on('ping')
def handle_ping():
    print(f'Received ping from \'{request.sid}\'')
    emit('pong', {'timestamp': datetime.now().isoformat()})

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

@app.route('/is-armed', methods=['POST'])
def is_armed():
    return {'isArmed': is_armed}