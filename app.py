import os
import logging
import traceback

import eventlet # Must be imported before Flask/SocketIO if async_mode='eventlet'

eventlet.hubs.use_hub("eventlet.hubs.asyncio") # Use asyncio hub before monkey patching
eventlet.monkey_patch() # Patch standard library early

from flask import Flask
from flask_socketio import SocketIO

import socket_events
import flask_routes
import utils.state as state
from utils.config import CONFIG
from utils.event_handler import EventHandler
from utils.async_helper import run_async_in_eventlet
from objects.ice_queue import ICEEventQueue
from objects.sid_manager import SIDManager
from onvif_.monitor_events import ONVIFMonitor


# Load log level config
LOG_LEVEL_ENV = os.getenv('LOG_LEVEL', 'INFO').upper()
VALID_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

log = logging.getLogger('main')

if LOG_LEVEL_ENV in VALID_LOG_LEVELS:
    logging_level = getattr(logging, LOG_LEVEL_ENV)
else:
    logging_level = logging.INFO # Default to INFO if environment variable is invalid
    log.warning(f"Invalid LOG_LEVEL '{LOG_LEVEL_ENV}' provided. Defaulting to INFO.")

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=logging_level,
    datefmt='%m/%d/%Y %I:%M:%S %p',
)

# Load app
app = Flask(__name__)
sio = SocketIO(app,
               cors_allowed_origins='*',
               logger=False, # Set to True for SocketIO specific logs
               engineio_logger=False, # Set to True for EngineIO specific logs
               async_mode='eventlet', # Use eventlet as async mode
               transports=['websocket', 'polling'],
               ping_timeout=2,
               ping_interval=.1)
event_queue = ICEEventQueue(sio)
sid_manager = SIDManager(sio)
event_handler = EventHandler(sio, event_queue)
onvif_monitor = ONVIFMonitor(event_handler)

# Register all Socket.IO event handlers
socket_events.register_socketio(sio, event_queue, sid_manager, event_handler)

# Register all HTTP API routes
flask_routes.register_api_routes(app, sio, event_queue)

def main():
    try:
        # Start background worker greenlets
        worker_pool = eventlet.GreenPool()
        check_old_clients_and_events_greenlet = worker_pool.spawn(event_queue.check_old_clients_and_events_worker)
        check_old_sids_greenlet = worker_pool.spawn(sid_manager.check_old_sids_worker)
        onvif_event_monitoring_greenlet = worker_pool.spawn(
            run_async_in_eventlet,
            onvif_monitor.onvif_event_monitoring_worker(
                socketio_instance=sio,
                event_queue_instance=event_queue
            )
        )

        log.info("Starting main server...")
        log.info(f"Listening on \'{CONFIG.host}:{CONFIG.port}\'...")
        sio.run(app,
                host=CONFIG.host,
                port=CONFIG.port,
                debug=False,
                use_reloader=False)

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

if __name__ == '__main__':
    main()