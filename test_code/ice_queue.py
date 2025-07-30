import logging
import datetime
import threading
from typing import List, Dict, Tuple

import eventlet
# WARNING: Add eventlet.monkey_patch() in main app

from flask_socketio import SocketIO

import state
from ice_event import ICEEvent
from ice_client import ICEClient

CLIENT_INVALID_THRESHOLD_SECONDS = 2 # 2 seconds
CLIENT_DELETE_THRESHOLD_SECONDS = 30 # 30 seconds

log = logging.getLogger(__name__)


class ICEEventQueue:
    """
    Manages a thread-safe event queue for multiple clients.
    """
    def __init__(self, socketio_instance: SocketIO):
        self.last_event_id: str = None
        self.sio: SocketIO = socketio_instance
        self.queue: Dict[str, ICEClient] = {}
        self.lock = threading.Lock()

    def add_client(self, client_name: str, client_type: str) -> None:
        """
        Adds a client from the queue.

        Args:
            client_name (str): Client Name
            client_type (str): Client Type
        """
        client = ICEClient(client_name,
                           client_type,
                           self.last_event_id)
        with self.lock:
            if client_name not in self.queue:
                self.queue[client_name] = client
                log.info(f'Client \'{client.client_name}\' added to the queue.')
            else:
                log.debug(f'Client \'{client_name}\' already exists in the queue. Updating timestamp.')
                self.queue[client_name].last_seen = datetime.datetime.now()

    def remove_client(self, client_name: str) -> bool:
        """
        Removes a client from the queue.

        Args:
            client_name (str): Client Name

        Returns:
            bool: True if the client was found and removed, False otherwise.
        """
        with self.lock:
            if client_name in self.queue:
                del self.queue[client_name]
                log.debug(f'Client \'{client_name}\' removed from the queue.')
                return True
            log.debug(f'Attempted to remove non-existent client \'{client_name}\' from the queue.')
            return False

    def get_client(self, client_name: str) -> ICEClient:
        """
        Returns the client object for a given client name.

        Args:
            client_name (str): Client Name

        Returns:
            ICEClient: The client object if found, None otherwise.
        """
        return self.queue.get(client_name, None)

    def add_event(self, event: ICEEvent) -> None:
        """
        Adds an event to all active clients' queues.

        Args:
            event (ICEEvent): The event object to add.
        """
        with self.lock:
            for client_name, client in self.queue.items():
                self.queue[client_name].events.append(event)
                log.debug(f'Event \'{event.event_name}\' added to client \'{client_name}\'.')
            self.last_event_id = event.event_id
    
    def get_events(self, client_name: str) -> Tuple[bool, List[ICEEvent]]:
        """
        Retrieves all events for a specific client.

        Args:
            client_name (str): Client Name

        Returns:
            Tuple[bool, List[ICEEvent]]: (True, events) if client found, (False, []) if client not found.
        """
        with self.lock:
            if client_name in self.queue:
                return True, self.queue[client_name].events
            log.error(f'Attempted to get events for non-existent client \'{client_name}\'.')
            return False, []
    
    def ack_events(self, client_name: str, event_id_list: List[str]) -> bool:
        """
        ACK event_ids for a client and updates last seen timestamp.

        Args:
            client_name (str): Client Name
            event_id_list (List[str]): List of event IDs to ACK.

        Returns:
            bool: Result of ACKing events.
        """
        new_events_list = []
        with self.lock:
            if client_name in self.queue:
                for event in self.queue[client_name].events:
                    if event.event_id not in event_id_list:
                        new_events_list.append(event)
                self.queue[client_name].events = new_events_list
                self.queue[client_name].last_seen = datetime.datetime.now()
                self.queue[client_name].alive = True
                return True
            
            log.error(f'Attempted to ACK events for non-existent client \'{client_name}\'.')
            return False
    
    def update_last_seen(self, client_name: str) -> bool:
        """
        Updates the last seen timestamp for a client.

        Args:
            client_name (str): Client Name

        Returns:
            bool: Result of updating last seen timestamp.
        """
        with self.lock:
            if client_name in self.queue:
                self.queue[client_name].last_seen = datetime.datetime.now()
                self.queue[client_name].alive = True
                return True
            log.error(f'Attempted to update last seen timestamp for non-existent client \'{client_name}\'.')
            return False

    def _check_old_clients(self):
        """
        Removes inactive clients from the queue.
        """
        clients_to_delete = []
        with self.lock:
            current_time = datetime.datetime.now()
            for client_name, client in self.queue.items():
                time_diff = current_time - client.last_seen
                if time_diff.total_seconds() > CLIENT_DELETE_THRESHOLD_SECONDS:
                    clients_to_delete.append(client_name)
                elif time_diff.total_seconds() > CLIENT_INVALID_THRESHOLD_SECONDS:
                    self.queue[client_name].alive = False
                    ### TODO: Broadcast
            
            for client_name in clients_to_delete:
                ### TODO: Broadcast
                log.info(f"Removing client '{client_name}' due to inactivity.")
                del self.queue[client_name]
    
    def check_old_clients_worker(self):
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