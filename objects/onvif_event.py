from typing import Any

class ONVIFEvent:
    """Simplified Event class to hold parsed event data."""
    def __init__(self, topic: str, value: Any | None = None, event_name: str | None = None, raw_message: Any | None = None):
        self.topic = topic
        self.value = value
        self.event_name = event_name # Custom event name from EVENT_DICT (e.g., 'motion', 'person')
        self.raw_message = raw_message # The original full message object

    def __repr__(self):
        return (
            f"Event(topic='{self.topic}', event_name='{self.event_name}', value='{self.value}', "
            f"source_data={self.source_data}, raw_message_type={type(self.raw_message)})"
        )
    def __str__(self):
        # Prefer custom event name if available, otherwise use topic
        display_name = self.event_name if self.event_name else self.topic
        return f"Event: \'{display_name}\', Value: \'{self.value}\', Topic: \'{self.topic}\'"