import uuid
import logging
import datetime
import threading
from typing import List, Dict, Tuple, TYPE_CHECKING

import eventlet
# WARNING: Add eventlet.monkey_patch() in main app

import utils.state as state
from objects.ice_event import ICEEvent
from objects.ice_client import ICEClient

if TYPE_CHECKING:
    from utils.event_handler import EventHandler


CLIENT_INVALID_THRESHOLD_SECONDS = 2 # 2 seconds
CLIENT_DELETE_THRESHOLD_SECONDS = 30 # 30 seconds
EVENT_INVALID_THRESHOLD_SECONDS = 15 # 15 seconds

log = logging.getLogger(__name__)


class ICEEventQueue:
    """
    Manages a thread-safe event queue for multiple clients.
    """
    def __init__(self, event_handler_instance: 'EventHandler'):
        self.last_event_id: str = None
        self._eh: 'EventHandler' = event_handler_instance
        self.queue: Dict[str, ICEClient] = {}
        self.event_list: List[ICEEvent] = []
        self.lock = threading.Lock()

    def add_client(self, sid: str, client_name: str, client_type: str) -> ICEClient:
        """
        Adds a client from the queue.

        Args:
            sid (str): SID
            client_name (str): Client Name
            client_type (str): Client Type
        """
        client = ICEClient(sid,
                           client_name,
                           client_type,
                           self.last_event_id)
        with self.lock:
            if client_name not in self.queue:
                self.queue[client_name] = client
                log.debug(f'Client \'{client.name}\' added to the queue.')
            else:
                log.debug(f'Client \'{client_name}\' already exists in the queue. Updating...')
                self.queue[client_name].sid = sid
                self.queue[client_name].last_seen = datetime.datetime.now()
                self.queue[client_name].alive = True

            return self.queue[client_name]

    def remove_client(self, sid: str) -> bool:
        """
        Removes a client from the queue.

        Args:
            client_name (str): Client Name

        Returns:
            bool: True if the client was found and removed, False otherwise.
        """
        with self.lock:
            client = self.get_client(sid)
            if client is None:
                log.debug(f'Attempted to remove non-existent client \'{sid}\' from the queue.')
                return False

            log.debug(f'Client \'{sid}\' (Client name: \'{client.name}\') removed from the queue.')
            del self.queue[client.name]
            return True

    def get_client(self, sid: str) -> ICEClient:
        """
        Returns the client object for a given SID.

        Args:
            sid (str): SID

        Returns:
            ICEClient: The client object if found, None otherwise.
        """
        for client_name, client in self.queue.items():
            if client.sid == sid:
                return client
        return None

    def get_client_list(self, client_type: str, is_alive: bool, json_friendly: bool) -> List[ICEClient]:
        """
        Gets the client.

        Args:
            client_type (str): Client Type
            is_alive (bool): Whether to filter only alive clients

        Returns:
            List[ICEClient]: List of requested clients
        """

        client_list = []
        with self.lock:
            for client_name, client in self.queue.items():
                if is_alive:
                    if client.alive and client.type == client_type:
                        if json_friendly:
                            client_list.append(client.to_dict(json_friendly=True))
                        else:
                            client_list.append(client)
                else:
                    if client.type == client_type:
                        if json_friendly:
                            client_list.append(client.to_dict(json_friendly=True))
                        else:
                            client_list.append(client)
        return client_list

    def add_event(self, event: ICEEvent) -> None:
        """
        Adds an event to all active clients' queues.

        Args:
            event (ICEEvent): The event object to add.
        """
        with self.lock:
            self.event_list.append(event)

            for client_name, client in self.queue.items():
                self.queue[client_name].events.append(event)
                log.debug(f'Event \'{event.name}\' added to client \'{client_name}\'.')
            self.last_event_id = event.id

    def get_events(self, sid: str) -> Tuple[bool, List[ICEEvent]]:
        """
        Retrieves all events for a specific client.

        Args:
            sid (str): SID

        Returns:
            Tuple[bool, List[ICEEvent]]: (True, events) if client found, (False, []) if client not found.
        """
        with self.lock:
            client = self.get_client(sid)
            if client is None:
                log.error(f'Attempted to get events for non-existent client \'{sid}\'.')
                return False, []
            else:
                return True, client.events

    def is_previous_event_valid(self, event_name: str) -> bool:
        with self.lock:
            for event in reversed(self.event_list):
                if event.name == event_name:
                    time_now = datetime.datetime.now()
                    time_diff = time_now - event.timestamp

                    if time_diff.total_seconds() <= EVENT_INVALID_THRESHOLD_SECONDS:
                        return True
            return False

    def ack_events(self, sid: str, event_id_list: List[str]) -> bool:
        """
        ACK event_ids for a client and updates last seen timestamp.

        Args:
            sid (str): SID
            event_id_list (List[str]): List of event IDs to ACK.

        Returns:
            bool: Result of ACKing events.
        """
        with self.lock:
            client = self.get_client(sid)
            new_events_list = []

            if client is None:
                log.error(f'Attempted to ACK events for non-existent client \'{sid}\'.')
                return False

            for event in self.queue[client.name].events:
                if str(event.id) not in event_id_list:
                    new_events_list.append(event)

            self.queue[client.name].events = new_events_list
            self.queue[client.name].last_seen = datetime.datetime.now()
            self.queue[client.name].alive = True

            return True

    def restore_queue(self, sid: str, event_id: str) -> bool:
        try:
            with self.lock:
                client = self.get_client(sid)
                if client is None:
                    log.error(f'Attemped to restore event queue for non-existent client \'{sid}\' with event id \'{event_id}\'')
                    return False

                new_event_queue = []
                for event in reversed(self.event_list):
                    if event.id != event_id:
                        new_event_queue.append(event)
                    else:
                        break
                new_event_queue = reversed(new_event_queue)

                self.queue[client.name].last_fetched_event_id = event_id
                self.queue[client.name].events = new_event_queue

                return True

        except:
            log.error(f'Error while restoring event queue for client \'{sid}\' with event id \'{event_id}\'')
            return False

    def update_last_seen(self, sid: str) -> bool:
        """
        Updates the last seen timestamp for a client.

        Args:
            client_name (str): Client Name

        Returns:
            bool: Result of updating last seen timestamp.
        """
        with self.lock:
            client = self.get_client(sid)
            if client is None:
                log.error(f'Attempted to update last seen timestamp for non-existent client \'{sid}\'.')
                return False

            self.queue[client.name].last_seen = datetime.datetime.now()
            self.queue[client.name].alive = True
            return True

    def _check_old_clients_and_events(self):
        """
        Removes inactive clients from the queue.
        """
        clients_to_delete: List[ICEClient] = []
        with self.lock:
            current_time = datetime.datetime.now()

            # Check and delete old events
            new_event_list = []
            for event in self.event_list:
                time_diff = current_time - event.timestamp
                if time_diff.total_seconds() <= EVENT_INVALID_THRESHOLD_SECONDS:
                    new_event_list.append(event)
            self.event_list = new_event_list

            # Check and delete old clients
            for client_name, client in self.queue.items():
                time_diff = current_time - client.last_seen
                if time_diff.total_seconds() > CLIENT_DELETE_THRESHOLD_SECONDS:
                    clients_to_delete.append(client)
                elif time_diff.total_seconds() > CLIENT_INVALID_THRESHOLD_SECONDS and client.alive == True:
                    log.info(f"Marking client '{client_name}' inactive due to inactivity.")
                    self.queue[client_name].alive = False

                    # Broadcast
                    event = ICEEvent(
                        event_id=uuid.uuid4(),
                        event_name='outdated',
                        event_type='client',
                        event_source='server',
                        event_data=client.to_dict(simplified=True, json_friendly=True)
                    )
                    self._eh.broadcast(event)

            for client in clients_to_delete:
                log.info(f"Removing client '{client.name}' due to inactivity.")
                del self.queue[client.name]

                # Broadcast
                event = ICEEvent(
                    event_id=uuid.uuid4(),
                    event_name='disconnected',
                    event_type='client',
                    event_source='server',
                    event_data=client.to_dict(simplified=True, json_friendly=True)
                )
                self._eh.broadcast(event)

    def check_old_clients_and_events_worker(self):
        """
        Worker that periodically cleans up old clients.
        """
        log.info("Client cleanup worker started.")
        while state.is_server_up:
            try:
                self._check_old_clients_and_events()
            except Exception as e:
                log.warning(f'Unexpected error occured while checking old clients and events: {e}')
            eventlet.sleep(0.1)
        log.info("Client cleanup worker stopped.")