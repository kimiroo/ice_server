import datetime
from typing import Dict, List, Any

from ice_event import ICEEvent

VALID_CLIENT_TYPE = [
    'html',
    'pc',
    'ha'
]


class ICEClient:
    """
    Represents an ICE client.
    """
    def __init__(self,
                 client_name: str,
                 client_type: str,
                 current_event_id: str):
        """
        Initializes an ICEClient object.

        Args:
            client_name (str): The name of the client.
            client_type (str):
        """
        if client_type not in VALID_CLIENT_TYPE:
            raise ValueError(f'\'{client_type}\' is not a valid client type.')

        self.client_name: str = client_name
        self.client_type: str = client_type
        self.registered: datetime.datetime = datetime.datetime.now()
        self.last_seen: datetime.datetime = datetime.datetime.now()
        self.alive: bool = True
        self.last_fetched_event_id: str = current_event_id
        self.events: List[ICEEvent] = []


    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the ICEClient object to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the client.
        """
        return {
            'client_name': self.client_name,
            'client_type': self.client_type,
            'registered': self.registered,
            'last_seen': self.last_seen,
            'alive': self.alive,
            'last_fetched_event_id': self.last_fetched_event_id,
            'events': self.events
        }