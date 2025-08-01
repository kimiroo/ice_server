import datetime
from typing import Dict, Any

class ICEEvent:
    """
    Represents an ICE (Information, Communication, Event) event with a name, data, and timestamp.
    """
    def __init__(self,
                 event_id: str,
                 event_name: str,
                 event_source: str,
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
        self.id: str = event_id
        self.name: str = event_name
        self.source: str = event_source
        self.data: Dict[str, Any] = event_data
        # Assign current time if timestamp is not provided
        self.timestamp: datetime.datetime = event_timestamp if event_timestamp is not None else datetime.datetime.now()

    def to_dict(self, json_friendly: bool = False) -> Dict[str, Any]:
        """
        Converts the ICEEvent object to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the event.
        """
        return {
            'id': self.id,
            'name': self.name,
            'source': self.source,
            'data': self.data,
            'timestamp': self.timestamp if not json_friendly else self.timestamp.isoformat()
        }