import logging
import datetime
import threading
from typing import Dict, List, Any

import eventlet
# WARNING: Add eventlet.monkey_patch() in main app

from flask_socketio import SocketIO

import state

SID_DELETE_THRESHOLD_SECONDS = 5 # 5 seconds

log = logging.getLogger(__name__)


class SIDObject:
    """
    Represents a SID object with its last seen timestamp.
    """
    def __init__(self, sid: str, client_name: str):
        """
        Initializes a SIDObject object.

        Args:
            sid (str): The SID of the client.
            client_name (str): The name of the client.
        """
        self.sid: str = sid
        self.client_name: str = client_name
        self.last_seen: datetime.datetime = datetime.datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the SIDObject object to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the SIDObject.
        """
        return {
            'sid': self.sid,
            'client_name': self.client_name,
            'last_seen': self.last_seen
        }
        

class SIDManager:
    """
    Manages a thread-safe dictionary of SIDs with their last seen timestamps.
    """
    def __init__(self, socketio_instance: SocketIO):
        self.sid_dict: Dict[str, SIDObject] = {}
        self.sio: SocketIO = socketio_instance
        self.lock = threading.Lock()

    def add_sid(self, sid: str, client_name: str) -> None:
        """
        Adds or updates a SID in the dictionary.

        Args:
            sid (str): The SID to add or update.
            client_name (str): The name of the client associated with the SID.
        """
        with self.lock:
            sid_object = SIDObject(sid, client_name)
            self.sid_dict[sid] = sid_object

    def remove_sid(self, sid: str) -> bool:
        """
        Removes a SID from the dictionary.

        Args:
            sid (str): The SID to remove.

        Returns:
            bool: True if the SID was found and removed, False otherwise.
        """
        with self.lock:
            if sid in self.sid_dict:
                del self.sid_dict[sid]
                log.debug(f'Client \'{sid}\' removed from the queue.')
                return True
            log.debug(f'Attempted to remove non-existent client \'{sid}\' from the queue.')
            return False

    def get_sid_object(self, sid: str) -> SIDObject:
        """
        Returns the SIDObject for a given SID.

        Args:
            sid (str): The SID to retrieve.

        Returns:
            SIDObject: The SIDObject if found, None otherwise.
        """
        return self.sid_dict.get(sid, None)
    
    def get_sid_list(self, client_name: str) -> List[str]:
        sid_list = []
        with self.lock:
            for sid, sid_object in self.sid_dict.items():
                if sid_object.client_name == client_name:
                    sid_list.append(sid)
        return sid_list

    def update_sid_timestamp(self, sid: str) -> bool:
        """
        Updates the timestamp for a given SID.

        Args:
            sid (str): The SID to update.

        Returns:
            bool: True if the SID was found and updated, False otherwise.
        """
        with self.lock:
            if sid in self.sid_dict:
                self.sid_dict[sid].last_seen = datetime.datetime.now()
                return True
            log.debug(f'Attempted to update timestamp for non-existent client \'{sid}\' from the queue.')
            return False

    def get_sids(self) -> dict:
        """
        Returns a copy of the current SID dictionary.

        Returns:
            dict: A copy of the sid_dict.
        """
        with self.lock:
            return self.sid_dict.copy()

    def _check_and_delete_old_sids(self):
        """
        Removes inactive SIDs from the dictionary.
        """
        sids_to_delete = []
        with self.lock:
            current_time = datetime.datetime.now()
            for sid, timestamp in self.sid_dict.items():
                time_diff = current_time - timestamp
                if time_diff.total_seconds() > SID_DELETE_THRESHOLD_SECONDS:
                    sids_to_delete.append(sid)
            
            for sid in sids_to_delete:
                del self.sid_dict[sid]
                log.info(f"Removing SID '{sid}' due to inactivity.")

    def check_and_delete_old_sids_worker(self):
        """
        Worker that periodically cleans up old SIDs.
        """
        log.info("SID cleanup worker started.")
        while state.is_server_up:
            try:
                self._check_and_delete_old_sids()
            except Exception as e:
                log.warning(f'Unexpected error occured while checking and deleting old SIDs: {e}')
            eventlet.sleep(0.1)
        log.info("SID cleanup worker stopped.")