# --- Global Application State Variables ---
is_armed = False
is_normal = True
is_server_up = True
connected_clients = {} # Stores client SID -> client_info_dict

# --- Configuration Constants ---
ALIVE_THRESHOLD_MS = 100 # In milliseconds
RECONNECT_DELAY_SECONDS = 5 # Delay for reconnect attempts

# --- Room Definitions ---
ROOM_HTML = 'room_html'
ROOM_PC = 'room_pc'
ROOM_HA = 'room_ha'