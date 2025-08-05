from typing import Any

class ONVIFEvent:
    """Simplified Event class to hold parsed event data."""
    def __init__(self,
                 topic: str,
                 value: Any | None = None,
                 event_name: str | None = None,
                 raw_message: Any | None = None):

        self.topic = topic
        self.value = value
        self.event_name = event_name # Custom event name from EVENT_DICT (e.g., 'motion', 'person')
        self.raw_message = raw_message # The original full message object