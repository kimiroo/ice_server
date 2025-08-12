import datetime
from typing import List

from objects.event import Event

class Client:
    def __init__(self, sid: str) -> None:
        self.sid: str = sid
        self.name: str | None = None
        self.type: str | None = None
        self.events: List[Event] = []
        self.registered: datetime = datetime.datetime.now()
        self.last_seen: datetime = datetime.datetime.now()

    def update(self, client_name: str, client_type: str) -> None:
        self.name = client_name
        self.type = client_type

    def update_last_seen(self) -> None:
        self.last_seen = datetime.datetime.now()

    def add_event(self, event: Event) -> None:
        self.events.append(event)

    def ack_event(self, event_id: str) -> None:
        for event in self.events:
            if str(event.id) == event_id:
                self.events.remove(event)
                break

    def restore_events(self, event_list: List[Event]) -> None:
        self.events = event_list

    def to_dict(self, json_friendly: bool):
        client_obj = {
            'sid': self.sid,
            'name': self.name,
            'type': self.type,
            'registered': self.registered.isoformat() if json_friendly else self.registered,
            'last_seen': self.last_seen.isoformat() if json_friendly else self.last_seen
        }
        return client_obj