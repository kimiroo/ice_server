import logging
import traceback

import eventlet # Must be imported before Flask/SocketIO if async_mode='eventlet'
eventlet.monkey_patch() # Patch standard library early

from flask import Flask
from flask_socketio import SocketIO

import test_sio as socket_events
from ice_queue import ICEEventQueue
from sid_manager import SIDManager

HOST = '0.0.0.0'
PORT = 8080

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=logging.DEBUG,
    datefmt='%m/%d/%Y %I:%M:%S %p',
)
log = logging.getLogger('main')

app = Flask(__name__)
sio = SocketIO(app,
               cors_allowed_origins='*',
               logger=False, # Set to True for SocketIO specific logs
               engineio_logger=False, # Set to True for EngineIO specific logs
               async_mode='eventlet', # Use eventlet as async mode
               transports=['websocket', 'polling'],
               ping_timeout=2,
               ping_interval=.1)
queue = ICEEventQueue(sio)
sidm = SIDManager(sio)

# Register all Socket.IO event handlers
socket_events.register_socketio(sio, queue, sidm)

# Register all HTTP API routes
#flask_routes.register_api_routes(app, socketio)

def main():
    try:
        # Start background worker greenlets
        worker_pool = eventlet.GreenPool()

        log.info("Starting main server...")
        log.info(f"Listening on \'{HOST}:{PORT}\'...")
        sio.run(app,
                host=HOST,
                port=PORT,
                debug=False,
                use_reloader=False)

    except KeyboardInterrupt:
        log.info('Shutting down... (reason: user interrupt)')
    except Exception as e:
        log.error(f'An unexpected error occurred: {e}')
        traceback.print_exc() # Print full traceback
    finally:
        log.info("Signaling workers to stop...")
        #state.is_server_up = False # Signal workers to stop gracefully
        # Give workers a moment to finish their current loop iteration
        eventlet.sleep(0.5)
        # You might want to join the greenlets if they have critical cleanup,
        # but for daemon-like workers, setting the flag is often enough.
        log.info("Server cleanup complete. Application terminated.")