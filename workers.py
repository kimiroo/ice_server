import datetime
import logging
import eventlet
from flask_socketio import SocketIO

import state
from rtsp import RTSP

log = logging.getLogger(__name__)

def check_alive_status():
    """Checks and updates the 'alive' status of connected clients."""
    time_now = datetime.datetime.now()
    # Iterate over a copy of items to avoid RuntimeError if connected_clients changes during iteration
    for sid, client in list(state.connected_clients.items()):
        time_diff = time_now - client['last_seen']
        # Convert timedelta to milliseconds for comparison
        time_diff_ms = time_diff.total_seconds() * 1000

        if time_diff_ms > state.ALIVE_THRESHOLD_MS:
            if state.connected_clients[sid]['alive']: # Only log if status changes
                log.info(f"Client {client['name']} (SID: {sid}) is now considered DEAD.")
            state.connected_clients[sid]['alive'] = False
        else:
            if not state.connected_clients[sid]['alive']: # Only log if status changes
                log.info(f"Client {client['name']} (SID: {sid}) is now considered ALIVE.")
            state.connected_clients[sid]['alive'] = True

def check_alive_status_worker():
    """Worker loop for checking client alive status."""
    log.info("Alive status checker worker started.")
    while state.is_server_up:
        try:
            check_alive_status()
        except Exception as e:
            log.critical(f'Error while running ICE system checker worker: {e}')
        eventlet.sleep(0.1)

    log.info("Alive status checker worker stopped.")

def check_ice_system():
    """ICE system health check."""
    # TODO: Implement ICE system specific checks here
    pass

def check_ice_system_worker():
    """Worker loop for checking ICE system health."""
    log.info("ICE system checker worker started.")
    while state.is_server_up:
        try:
            check_ice_system()
        except Exception as e:
            log.critical(f'Error while running ICE system checker worker: {e}')
        eventlet.sleep(0.1)

    log.info("ICE system checker worker stopped.")

def manage_ha_event_list():
    """Check and clears HA events list"""
    time_now = datetime.datetime.now()
    for event_name, event in list(state.ha_events_list.items()):
        time_diff = time_now - event['timestamp']
        time_diff = time_diff.total_seconds() # Convert to float seconds

        if time_diff > state.HA_EVENT_IGNORE_SECONDS and state.ha_events_list[event_name]['is_valid']:
            log.info(f"HA Event \'{event_name}\' is now considered INVALID.")
            state.ha_events_list[event_name]['is_valid'] = False

def manage_ha_event_list_worker():
    """Worker loop for checking HA events list."""
    log.info("HA event manager worker started.")
    while state.is_server_up:
        try:
            manage_ha_event_list()
        except Exception as e:
            log.critical(f'Error while running HA event manager worker: {e}')
        eventlet.sleep(0.1)

    log.info("HA event manager worker stopped.")

def stream_rtsp(sio_instance: SocketIO, rtsp_instance: RTSP):
    """Fetch a frame from RTSP and streams via SocketIO"""
    if rtsp_instance.is_streaming() and rtsp_instance.is_open() and state.is_armed:
        eventlet.spawn(sio_instance.emit, 'video_frame', {
                'frame': rtsp_instance.get_frame(),
                'timestamp': datetime.datetime.now().isoformat()
            },
            room=state.ROOM_HTML
        )

def stream_rtsp_worker(sio_instance: SocketIO, rtsp_instance: RTSP):
    """Worker loop for streamding RTSP feed."""
    log.info("RTSP stream worker started.")
    while state.is_server_up:
        try:
            stream_rtsp(sio_instance, rtsp_instance)
        except Exception as e:
            log.critical(f'Error while running RTSP stream worker: {e}')
        eventlet.sleep(0.0333333333333333)

    log.info("RTSP stream worker stopped.")