import logging
import datetime
import threading
from typing import List, Dict, Tuple, Union, Any, Optional

import eventlet
# WARNING: Add eventlet.monkey_patch() in main app

import state
from ice_event import ICEEvent

CLIENT_DELETE_THRESHOLD_SECONDS = 5 * 60 # 5 minutes

log = logging.getLogger(__name__)

# Type alias for the client information dictionary
ClientInfo = Dict[str, Union[datetime.datetime, List[ICEEvent]]]

class ICEEventQueue:
    """
    Manages a thread-safe event queue for multiple clients.
    """
    def __init__(self):
        self.last_event_id = None
        self.queue = {}
        self.lock = threading.Lock()

    def add_client(self, client_id: str) -> None:
        """
        Adds a client from the queue.

        Args:
            client_id (str): Client ID
        """
        with self.lock:
            if client_id not in self.queue:
                self.queue[client_id] = {
                    'added_timestamp': datetime.datetime.now(),
                    'last_seen_timestamp': datetime.datetime.now(),
                    'last_fetched_event_id': self.last_event_id,
                    'events': []
                }
                log.info(f'Client \'{client_id}\' added to the queue.')
            else:
                log.debug(f'Client \'{client_id}\' already exists in the queue. Updating timestamp.')
                self.queue[client_id]['last_seen_timestamp'] = datetime.datetime.now()

    def remove_client(self, client_id: str) -> bool:
        """
        Removes a client from the queue.

        Args:
            client_id (str): Client ID

        Returns:
            bool: True if the client was found and removed, False otherwise.
        """
        with self.lock:
            if client_id in self.queue:
                del self.queue[client_id]
                log.debug(f'Client \'{client_id}\' removed from the queue.')
                return True
            log.debug(f'Attempted to remove non-existent client \'{client_id}\' from the queue.')
            return False

    def add_event(self, event: ICEEvent) -> None:
        """
        Adds an event to all active clients' queues.

        Args:
            event (ICEEvent): The event object to add.
        """
        with self.lock:
            for client_id, client_queue in self.queue.items():
                self.queue[client_id]['events'].append(event)
                log.debug(f'Event \'{event.event_name}\' added to client \'{client_id}\'.')
            self.last_event_id = event.event_id
    
    def get_events(self, client_id: str) -> Tuple[bool, List[ICEEvent]]:
        """
        Retrieves all events for a specific client.

        Args:
            client_id (str): Client ID.

        Returns:
            Tuple[bool, List[ICEEvent]]: (True, events) if client found, (False, []) if client not found.
        """
        with self.lock:
            if client_id in self.queue:
                self.queue[client_id]['last_fetched_event_id'] = self.last_event_id
                return self.queue[client_id]['events']
            log.warning(f'Attempted to get events for non-existent client \'{client_id}\'.')
            return []
    
    def clear_events(self, client_id) -> bool:
        """
        Clears events for a client and updates last seen timestamp. Also acts as ACK.

        Args:
            client_id (str): Client ID.

        Returns:
            bool: Result of clearing client's events.
        """
        with self.lock:
            if client_id in self.queue:
                events_list = self.queue[client_id]['events']

                if self.queue[client_id]['last_fetched_event_id'] == self.last_event_id:
                    self.queue[client_id]['events'] = []
                    self.queue[client_id]['last_seen_timestamp'] = datetime.datetime.now()
                    return True, events_list
                else:
                    log.warning(f'Last fetched queue is outdated for client \'{client_id}\'. Cannot clear events.')
                    return False, events_list

            log.warning(f'Attempted to clear events for non-existent client \'{client_id}\'.')
            return False, []
    
    def _check_and_delete_old_client(self):
        """
        Removes inactive clients from the queue.
        """
        with self.lock:
            for client_id, client_queue in self.queue.items():
                time_diff = datetime.datetime.now() - client_queue['last_seen_timestamp']
                if time_diff.total_seconds() > CLIENT_DELETE_THRESHOLD_SECONDS:
                    log.info(f"Removing client '{client_id}' due to inactivity.")
                    self.remove_client(client_id)
    
    def check_and_delete_old_client_worker(self):
        """
        Worker that periodically cleans up old clients.
        """
        log.info("Client cleanup worker started.")
        while state.is_server_up:
            try:
                self._check_and_delete_old_client()
            except Exception as e:
                log.warning(f'Unexpected error occured while checking and deleting old clients: {e}')
            eventlet.sleep(0.1)
        log.info("Client cleanup worker stopped.")