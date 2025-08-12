import datetime
from typing import Union

class Event:
    def __init__(self, event_id: str, event_event: str, event_type: str, event_source: str, event_data: Union[dict, None] = None) -> None:
        self.id: str = event_id
        self.event: str = event_event
        self.type: str = event_type
        self.source: str = event_source
        self.data: dict = event_data
        self.timestamp: datetime = datetime.datetime.now()

    def to_dict(self, json_friendly: bool) -> dict:
        event_obj = {
            'id': str(self.id) if json_friendly else self.id,
            'event': self.event,
            'type': self.type,
            'source': self.source,
            'data': self.data,
            'timestamp': self.timestamp.isoformat() if json_friendly else self.timestamp
        }
        return event_obj