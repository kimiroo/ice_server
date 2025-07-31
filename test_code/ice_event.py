import datetime
import uuid
from typing import Dict, Any

class ICEEvent:
    """
    Represents an ICE (Information, Communication, Event) event with a name, data, and timestamp.
    """
    def __init__(self,
                 event_name: str,
                 event_data: Dict[str, Any], # event_data can be a dictionary with various types
                 event_timestamp: datetime.datetime = None # Default to None and set inside for current time
                 ):
        """
        Initializes an ICEEvent object.

        Args:
            event_name (str): The name or type of the event.
            event_data (Dict[str, Any]): A dictionary containing the event's specific data.
            event_timestamp (datetime.datetime, optional): The timestamp of the event.
                                                             Defaults to the current time if not provided.
        """
        self.event_id: str = uuid.uuid4()
        self.event_name: str = event_name
        self.event_data: Dict[str, Any] = event_data
        # Assign current time if timestamp is not provided
        self.timestamp: datetime.datetime = event_timestamp if event_timestamp is not None else datetime.datetime.now()

    def to_dict(self, json_friendly: bool = False) -> Dict[str, Any]:
        """
        Converts the ICEEvent object to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the event.
        """
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "event_data": self.event_data,
            "timestamp": self.timestamp if not json_friendly else self.timestamp.isoformat()
        }