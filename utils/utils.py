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