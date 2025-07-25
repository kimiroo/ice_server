import datetime

# --- Configuration Constants ---
ALIVE_THRESHOLD_MS = 2000 # In milliseconds
RECONNECT_DELAY_SECONDS = 5 # Delay for reconnect attempts
HA_EVENT_IGNORE_SECONDS = 15

# --- Room Definitions ---
ROOM_HTML = 'room_html'
ROOM_PC = 'room_pc'
ROOM_HA = 'room_ha'

# --- Global Application State Variables ---
is_armed = False
is_normal = True
is_server_up = True
connected_clients = {} # Stores client SID -> client_info_dict

# --- Event Variables ---
ha_events_list = {}