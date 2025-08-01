import logging
import datetime
import threading
from typing import Dict, List

import eventlet
# WARNING: Add eventlet.monkey_patch() in main app

from flask_socketio import SocketIO

import utils.state as state
from objects.sid_object import SIDObject

SID_INVALID_THRESHOLD_SECONDS = 2 # 2 seconds
SID_DELETE_THRESHOLD_SECONDS = 30 # 30 seconds
CLIENT_TYPES_TO_TRACK = ['pc', 'ha', 'html']

log = logging.getLogger(__name__)


class SIDManager:
    """
    Manages a thread-safe dictionary of SIDs with their last seen timestamps.
    """
    def __init__(self, socketio_instance: SocketIO):
        self.sid_dict: Dict[str, SIDObject] = {}
        self.untracked_sid_dict: dict = {}
        self.sio: SocketIO = socketio_instance
        self.lock = threading.Lock()

    def add_sid(self, sid: str, client_name: str, client_type: str) -> None:
        """
        Adds or updates a SID in the dictionary.

        Args:
            sid (str): The SID to add or update.
            client_name (str): The name of the client associated with the SID.
        """
        with self.lock:
            if client_type in CLIENT_TYPES_TO_TRACK:
                sid_object = SIDObject(sid, client_name)
                self.sid_dict[sid] = sid_object
            else:
                self.untracked_sid_dict[sid] = {}

    def remove_sid(self, sid: str) -> bool:
        """
        Removes a SID from the dictionary.

        Args:
            sid (str): The SID to remove.

        Returns:
            bool: True if the SID was found and removed, False otherwise.
        """
        with self.lock:
            if sid in self.untracked_sid_dict:
                del self.untracked_sid_dict[sid]
            elif sid in self.sid_dict:
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

    def get_sid_list(self, client_name: str, is_alive: bool) -> List[str]:
        sid_list = []
        with self.lock:
            for sid, sid_object in self.sid_dict.items():
                if is_alive:
                    if sid_object.is_alive and sid_object.client_name == client_name:
                        sid_list.append(sid)
                else:
                    if sid_object.client_name == client_name:
                        sid_list.append(sid)
        return sid_list

    def update_last_seen(self, sid: str) -> bool:
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
                self.sid_dict[sid].is_alive = True
                return True
            log.debug(f'Attempted to update timestamp for non-existent client \'{sid}\' from the queue.')
            return False

    def get_sids(self, is_alive: bool, json_friendly: bool) -> dict:
        """
        Returns a copy of the current SID dictionary.

        Returns:
            dict: A copy of the sid_dict.
        """
        with self.lock:
            sid_list = []
            for sid, sid_object in self.sid_dict.items():
                if is_alive:
                    if sid_object.is_alive:
                        sid_list.append(sid_object.to_dict(json_friendly))
                else:
                    sid_list.append(sid_object.to_dict(json_friendly))
            return sid_list

    def is_test_client(self, sid: str) -> bool:
        """
        Checks if a SID is a test client.
        """
        return sid in self.untracked_sid_dict

    def _check_old_sids(self):
        """
        Removes inactive SIDs from the dictionary.
        """
        sids_to_delete = []
        with self.lock:
            time_now = datetime.datetime.now()
            for sid, sid_object in self.sid_dict.items():
                time_diff = time_now - sid_object.last_seen
                if time_diff.total_seconds() > SID_DELETE_THRESHOLD_SECONDS:
                    sids_to_delete.append(sid)
                elif time_diff.total_seconds() > SID_INVALID_THRESHOLD_SECONDS:
                    self.sid_dict[sid].is_alive = False
                    ### TODO: Broadcast

            for sid in sids_to_delete:
                ### TODO: Broadcast
                del self.sid_dict[sid]
                log.info(f"Removing SID '{sid}' due to inactivity.")

    def check_old_sids_worker(self):
        """
        Worker that periodically cleans up old SIDs.
        """
        log.info("SID cleanup worker started.")
        while state.is_server_up:
            try:
                self._check_old_sids()
            except Exception as e:
                log.warning(f'Unexpected error occured while checking and deleting old SIDs: {e}')
            eventlet.sleep(0.1)
        log.info("SID cleanup worker stopped.")