import logging
import traceback

import eventlet # Must be imported before Flask/SocketIO if async_mode='eventlet'
eventlet.monkey_patch() # Patch standard library early

from flask import Flask
from flask_socketio import SocketIO

import state
import workers
import socket_events
import flask_routes

from rtsp import RTSP

HOST = '0.0.0.0'
PORT = 8080
RTSP_URL = 'rtsp://tapo_cam:zz%6k5CWYXc0tpTSqwS*qbgYD6!$axmK@10.5.21.10:554/stream1'

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=logging.DEBUG,
    datefmt='%m/%d/%Y %I:%M:%S %p',
)
log = logging.getLogger('main')

app = Flask(__name__)
socketio = SocketIO(app,
                    cors_allowed_origins='*',
                    logger=False, # Set to True for SocketIO specific logs
                    engineio_logger=False, # Set to True for EngineIO specific logs
                    async_mode='eventlet', # Use eventlet as async mode
                    transports=['websocket', 'polling'],
                    ping_timeout=2,
                    ping_interval=.1)
rtsp = RTSP(RTSP_URL)

# Register all Socket.IO event handlers
socket_events.register_socket_events(socketio, rtsp)

# Register all HTTP API routes
flask_routes.register_api_routes(app, socketio, rtsp)

if __name__ == '__main__':
    try:
        # Start background worker greenlets
        worker_pool = eventlet.GreenPool()
        alive_checker_greenlet = worker_pool.spawn(workers.check_alive_status_worker)
        system_checker_greenlet = worker_pool.spawn(workers.check_ice_system_worker)
        ha_event_manager_greenlet = worker_pool.spawn(workers.manage_ha_event_list_worker)
        rtsp_streaming_greenlet = worker_pool.spawn(workers.stream_rtsp_worker, socketio, rtsp)

        log.info("Starting Socket.IO server...")
        log.info(f"Listening on \'{HOST}:{PORT}\'...")
        socketio.run(app,
                     host=HOST,
                     port=PORT,
                     debug=False, # Set to True for Flask reloader in development, but be careful with eventlet
                     use_reloader=False) # Important for eventlet to avoid double-spawning

    except KeyboardInterrupt:
        log.info('Shutting down... (reason: user interrupt)')
    except Exception as e:
        log.error(f'An unexpected error occurred: {e}')
        traceback.print_exc() # Print full traceback
    finally:
        log.info("Signaling workers to stop...")
        state.is_server_up = False # Signal workers to stop gracefully
        # Give workers a moment to finish their current loop iteration
        eventlet.sleep(0.5)
        # You might want to join the greenlets if they have critical cleanup,
        # but for daemon-like workers, setting the flag is often enough.
        log.info("Server cleanup complete. Application terminated.")