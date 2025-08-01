import datetime
from typing import Dict, Any

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
        self.is_alive: bool = True

    def to_dict(self, json_friendly: bool = False) -> Dict[str, Any]:
        """
        Converts the SIDObject object to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the SIDObject.
        """
        return {
            'sid': self.sid,
            'client_name': self.client_name,
            'last_seen': self.last_seen if not json_friendly else self.last_seen.isoformat(),
            'is_alive': self.is_alive
        }