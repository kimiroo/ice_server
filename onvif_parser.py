from __future__ import annotations
import logging
from typing import Any

# Ensure basic logging is configured if this snippet is run standalone for testing
# In the full script, this would be set up globally.
LOGGER = logging.getLogger(__name__)

# --- Custom Parser Definitions ---
EVENT_DICT = {
    'tns1:RuleEngine/CellMotionDetector/Motion': {
        'event': 'motion',
        'type': 'bool',
        'value_name': 'IsMotion'
    },
    'tns1:RuleEngine/PeopleDetector/People': {
        'event': 'person',
        'type': 'bool',
        'value_name': 'IsPeople'
    }
}

# --- Simplified Event Model for output ---
class Event:
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


# --- Unified Event Parser Function ---
async def parse_event_message(msg: Any) -> Event | None:
    """
    Parses a generic ONVIF event message using custom definitions or
    falls back to extracting all SimpleItem data.
    """
    # Check if msg has a valid topic structure before proceeding
    if not hasattr(msg, 'Topic') or not hasattr(msg.Topic, '_value_1'):
        LOGGER.debug("Received an event message without a valid topic, skipping.")
        return None

    topic = msg.Topic._value_1.rstrip("/.")
    parsed_event_name: str | None = None
    parsed_value: Any | None = None
    source_items_parsed: dict[str, str] = {}
    data_items_parsed: dict[str, str] = {}

    # 1. Extract source data (always try to do this)
    try:
        # Check for existence of Message, Source, and SimpleItem before iterating
        if hasattr(msg, 'Message') and \
           hasattr(msg.Message, 'Source') and \
           hasattr(msg.Message.Source, 'SimpleItem') and \
           msg.Message.Source.SimpleItem is not None: # Ensure SimpleItem is not None

            for item in msg.Message.Source.SimpleItem:
                if hasattr(item, 'Name') and hasattr(item, 'Value'):
                    source_items_parsed[item.Name] = item.Value
    except (AttributeError, TypeError, IndexError) as e:
        LOGGER.debug(f"Error extracting source data for topic {topic}: {e}")

    # 2. Try to use custom parser definitions from EVENT_DICT
    if topic in EVENT_DICT:
        config = EVENT_DICT[topic]
        parsed_event_name = config['event']
        target_value_name = config['value_name']
        value_type = config['type']

        try:
            # Check for existence of Message, _value_1, Data, and SimpleItem before iterating
            if hasattr(msg, 'Message') and \
               hasattr(msg.Message, '_value_1') and \
               hasattr(msg.Message._value_1, 'Data') and \
               hasattr(msg.Message._value_1.Data, 'SimpleItem') and \
               msg.Message._value_1.Data.SimpleItem is not None: # Ensure SimpleItem is not None

                # SimpleItem is often a list, so iterate. It could also be a single object.
                # Convert to a list if it's a single object for consistent iteration.
                simple_items = msg.Message._value_1.Data.SimpleItem
                if not isinstance(simple_items, list):
                    simple_items = [simple_items]

                for item in simple_items:
                    if hasattr(item, 'Name') and item.Name == target_value_name:
                        raw_value = item.Value
                        if value_type == 'bool':
                            parsed_value = (raw_value == 'true')
                        elif value_type == 'str':
                            parsed_value = raw_value
                        elif value_type == 'int':
                            try:
                                parsed_value = int(raw_value)
                            except ValueError:
                                LOGGER.warning(f"Could not convert '{raw_value}' to int for topic {topic}. Keeping as string.")
                                parsed_value = raw_value # Fallback to string if conversion fails
                        # Break after finding the target value name, as we only expect one primary value
                        break
        except (AttributeError, TypeError, IndexError) as e:
            # Log the specific error for custom parsing failure
            LOGGER.warning(f"Error in custom parsing for topic '{topic}' (target '{target_value_name}'): {e}. Falling back to generic parsing.")
            parsed_value = None # Reset parsed_value to trigger generic fallback

    # 3. Fallback: If custom parsing didn't find a value or topic not in filter, extract all data items
    if parsed_value is None: # Only if custom parsing failed or topic was not in EVENT_DICT
        try:
            if hasattr(msg, 'Message') and \
               hasattr(msg.Message, '_value_1') and \
               hasattr(msg.Message._value_1, 'Data') and \
               hasattr(msg.Message._value_1.Data, 'SimpleItem') and \
               msg.Message._value_1.Data.SimpleItem is not None:

                # Convert to a list if it's a single object for consistent iteration.
                simple_items_fallback = msg.Message._value_1.Data.SimpleItem
                if not isinstance(simple_items_fallback, list):
                    simple_items_fallback = [simple_items_fallback]

                for item in simple_items_fallback:
                    if hasattr(item, 'Name') and hasattr(item, 'Value'):
                        # Only add items not already processed by a successful custom parser attempt
                        # (This check is implicitly covered by parsed_value being None,
                        # but keeping in mind if more complex logic were here)
                        data_items_parsed[item.Name] = item.Value
        except (AttributeError, TypeError, IndexError) as e:
            LOGGER.debug(f"Error extracting generic data for topic {topic}: {e}")

        # Combine source and data items for generic value if no specific value was found
        combined_data_for_value = {**source_items_parsed, **data_items_parsed}
        if combined_data_for_value:
            # If there's only one item in combined_data, make its value the parsed_value for simplicity
            if len(combined_data_for_value) == 1:
                parsed_value = list(combined_data_for_value.values())[0]
            else:
                parsed_value = str(combined_data_for_value) # Convert dictionary to string for complex data
        else:
            parsed_value = "No specific data found"

    # Return the Event object with all collected information
    return Event(
        topic=topic,
        value=parsed_value,
        event_name=parsed_event_name,
        raw_message=msg # Store the full raw message for debugging if needed
    )