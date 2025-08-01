import datetime
from flask import request

import state

def identify_client(headers, sid):
    """Identifies client type and name from request headers."""
    client_type = headers.get('X-Client-Type', '')
    client_name = headers.get('X-Client-Name', None)

    if client_type in ['ha', 'pc', 'test'] and client_name:
        return client_type, client_name

    user_agent = headers.get('User-Agent', '')
    if 'Mozilla' in user_agent or 'Chrome' in user_agent or 'Safari' in user_agent:
        return 'html', f'html_{sid}'

    return 'unknown', None

def get_connected_client_list(client_type: str, only_alive: bool):
    """
    Returns a list of client detail dictionaries for a given type,
    optionally filtered by 'alive' status.
    """
    filtered_list = []

    for sid, client in state.connected_clients.items():

        if client_type == 'all' or client['type'] == client_type:
            if not only_alive or client['alive']: # `client['alive']` is assumed to be up-to-date
                client_obj = {
                    'clientName': client['name'],
                    'clientType': client['type'],
                    'connectedTime': client['connected_time'].isoformat(),
                    'lastSeen': client['last_seen'].isoformat(),
                    'alive': client['alive'],
                    'sid': sid
                }
                filtered_list.append(client_obj)

    return filtered_list