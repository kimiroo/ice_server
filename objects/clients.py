import datetime
import asyncio
from typing import Dict, List, Optional

from objects.client import Client
from objects.event import Event

CLIENT_REMOVAL_THRESHOLD = 1
EVENT_REMOVAL_THRESHOLD = 15

class Clients:
    def __init__(self) -> None:
        self._clients: Dict[str, Client] = {}
        self._events: List[Event] = []
        self._lock = asyncio.Lock()

    async def add_client(self, sid: str) -> None:
        async with self._lock:
            client = Client(sid)
            self._clients[sid] = client

    async def remove_client(self, sid: str) -> None:
        async with self._lock:
            if sid in self._clients:
                del self._clients[sid]

    async def update_client(self,
                            sid: str,
                            client_name: str,
                            client_type: str,
                            last_event_id: Optional[str] = None) -> None:
        async with self._lock:
            if sid in self._clients:
                client = self._clients[sid]
                client.update(client_name, client_type)
                client.update_last_seen()

                if last_event_id is not None:
                    new_event_list = []
                    for event in reversed(self._events):
                        if str(event.id) != last_event_id:
                            new_event_list.append(event)
                        else:
                            break
                    client.restore_events(new_event_list)

    async def get_client(self, sid: str) -> None:
        async with self._lock:
            if sid in self._clients:
                return self._clients[sid]

    async def update_last_seen(self, sid: str) -> None:
        async with self._lock:
            if sid in self._clients:
                self._clients[sid].update_last_seen()

    async def get_client_list(self, json_friendly: bool) -> List[dict]:
        async with self._lock:
            client_list = []
            for client in self._clients.values():
                if json_friendly:
                    client_list.append(client.to_dict(json_friendly))
                else:
                    client_list.append(client)
            return client_list

    async def add_event(self, event: Event) -> None:
        async with self._lock:
            self._events.append(event)

            for client in self._clients.values():
                client.add_event(event)

    async def get_event_list(self, sid: str, json_friendly: bool) -> List[dict]:
        async with self._lock:
            event_list = []
            if sid in self._clients:
                for event in self._clients[sid].events:
                    if json_friendly:
                        event_list.append(event.to_dict(json_friendly))
                    else:
                        event_list.append(event)
            return event_list

    async def ack_event(self, sid: str, event_id: str) -> None:
        async with self._lock:
            if sid in self._clients:
                self._clients[sid].ack_event(event_id)

    async def clean_client(self) -> List[str]:
        async with self._lock:
            time_now = datetime.datetime.now()
            deleted_client_sids = []
            for sid in list(self._clients.keys()):
                client = self._clients[sid]
                if (time_now - client.last_seen).total_seconds() > CLIENT_REMOVAL_THRESHOLD:
                    deleted_client_sids.append(sid)
                    del self._clients[sid]
            return deleted_client_sids

    async def clean_event(self) -> None:
        async with self._lock:
            for event in self._events:
                if (datetime.datetime.now() - event.timestamp).total_seconds() > EVENT_REMOVAL_THRESHOLD:
                    self._events.remove(event)
                    for client in self._clients.values():
                        client.ack_event(str(event.id))

    async def is_previous_event_valid(self, event_event: str) -> bool:
        async with self._lock:
            time_now = datetime.datetime.now()
            for event in reversed(self._events):
                time_diff = time_now - event.timestamp

                if event.event == event_event and time_diff.total_seconds() < EVENT_REMOVAL_THRESHOLD:
                    return True

            return False