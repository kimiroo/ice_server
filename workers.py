import datetime
import logging
import eventlet

import state

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
        check_alive_status()
        eventlet.sleep(0.1)

    log.info("Alive status checker worker stopped.")

def check_ice_system():
    """ICE system health check."""
    # Implement your ICE system specific checks here
    pass

def check_ice_system_worker():
    """Worker loop for checking ICE system health."""
    log.info("ICE system checker worker started.")
    while state.is_server_up:
        check_ice_system()
        eventlet.sleep(0.1)

    log.info("ICE system checker worker stopped.")