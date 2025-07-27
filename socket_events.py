import datetime
import logging
from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room

import state
import utils

log = logging.getLogger(__name__)

ROOM_HTML = state.ROOM_HTML
ROOM_PC = state.ROOM_PC
ROOM_HA = state.ROOM_HA

def register_socket_events(sio_instance: SocketIO):
    """Registers all Socket.IO event handlers with the given SocketIO instance."""

    @sio_instance.on('connect')
    def handle_connect():
        try:
            headers = dict(request.headers)
            client_type, client_name = utils.identify_client(headers, request.sid)

            log.info(f'Client connecting - Type: {client_type}, Name: {client_name}, SID: {request.sid}')

            if client_type == 'html':
                join_room(ROOM_HTML)
                log.info(f'HTML client \'{request.sid}\' joined \'{ROOM_HTML}\' room.')

            elif client_type == 'pc':
                if not client_name:
                    log.warning(f'PC client {request.sid} connected without client_name')
                    emit('error', {'message': 'client name is required for PC clients'})
                    return False
                join_room(ROOM_PC)
                log.info(f'PC client \'{client_name}\' (SID: {request.sid}) joined \'{ROOM_PC}\' room.')

            elif client_type == 'ha':
                if not client_name:
                    log.warning(f'HA client {request.sid} connected without client name')
                    emit('error', {'message': 'client name is required for HA clients'})
                    return False
                join_room(ROOM_HA)
                log.info(f'HA client \'{client_name}\' (SID: {request.sid}) joined \'{ROOM_HA}\' room.')

            elif client_type == 'test':
                if not client_name:
                    log.warning(f'TEST client {request.sid} connected without client name')
                    emit('error', {'message': 'client name is required for TEST clients'})
                    return False

            else:
                log.warning(f'Unknown client type for SID: {request.sid}')
                emit('error', {'message': 'Unknown client type'})
                return False

            emit('connected', {
                'status': 'success',
                'clientName': client_name,
                'clientType': client_type,
                'sid': request.sid
            })

            # Update global connected_clients state
            state.connected_clients[request.sid] = {
                'name': client_name,
                'type': client_type,
                'connected_time': datetime.datetime.now(),
                'last_seen': datetime.datetime.now(),
                'alive': True
            }

            if client_type in ['pc', 'ha']:
                sio_instance.emit(f'client_event', {
                    'event': 'connected',
                    'client': {
                        'clientName': client_name,
                        'clientType': client_type,
                        'sid': request.sid
                    }
                })

        except Exception as e:
            log.error(f'Error in handle_connect: {e}')
            emit('error', {'message': 'Connection failed'})
            return False

    @sio_instance.on('disconnect')
    def handle_disconnect():
        try:
            # Remove from connected clients list
            client = state.connected_clients.pop(request.sid, None)
            if client:
                log.info(f'{client['type'].upper()} client \'{client['name']}\' (SID: {request.sid}) disconnected.')

                if client['type'] in ['pc', 'ha']:
                    # Broadcast
                    sio_instance.emit('client_event', {
                        'event': 'disconnected',
                        'client': {
                            'clientName': client['name'],
                            'clientType': client['type'],
                            'sid': request.sid
                        }
                    })

            else:
                log.warning(f"Disconnected client SID {request.sid} not found in connected_clients.")
        except Exception as e:
            log.error(f'Error in handle_disconnect: {e}')

    @sio_instance.on('event_ha')
    def handle_ha_event(data):
        # Check basic event message structure
        event_name = data.get('event', None)
        event_id = data.get('id', None)

        if not event_name:
            log.error(f'Invalid HA event received: \'{data}\'. HA event must specify \'event\' field.')
            emit('event_result', {
                'id': event_id,
                'result': 'failed',
                'message': 'HA event must specify \'event\' field.'
            })
            return False

        if not event_id:
            log.error(f'Invalid HA event received: \'{data}\'. HA event must specify \'id\' field.')
            emit('event_result', {
                'id': event_id,
                'result': 'failed',
                'message': 'HA event must specify \'id\' field.'
            })
            return False

        # Ignore when disarmed
        if not state.is_armed:
            log.info(f'HA event \'{event_name}\' ignored. (reason: ICE is disarmed)')
            emit('event_result', {
                'id': event_id,
                'result': 'success',
                'message': 'HA event ignored. (reason: ICE is disarmed)'
            })
            return True

        # Check if previous HA event is still valid
        previus_event = state.ha_events_list.get(data.get('event'), None)
        proceed = False

        if not previus_event:
            proceed = True
        elif not previus_event.get('is_valid', False):
            proceed = True

        if not proceed:
            log.info(f'Previous HA event \'{event_name}\' is still valid. Ignoring this event...')
            emit('event_result', {
                'id': event_id,
                'result': 'success',
                'message': 'HA event ignored. (reason: previous event still valid)'
            })
            return True

        # Update state and broadcast event
        log.info(f'HA event \'{event_name}\' accepted. Broadcasting event...')
        state.ha_events_list[event_name] = {
            'id': event_id,
            'timestamp': datetime.datetime.now(),
            'is_valid': True
        }

        emit('event_result', {
            'id': event_id,
            'result': 'success',
            'message': 'HA event accepted and broadcasted.'
        })

        data['eventSource'] = 'ha'
        sio_instance.emit('event', data)

        return True

    @sio_instance.on('event_html')
    def handle_html_event(data):
        # Check basic event message structure
        event_name = data.get('event', None)
        event_id = data.get('id', None)

        if not event_name:
            log.error(f'Invalid HTML event received: \'{data}\'. HTML event must specify \'event\' field.')
            emit('event_result', {
                'id': event_id,
                'result': 'failed',
                'message': 'HTML event must specify \'event\' field.'
            })
            return False

        if not event_id:
            log.error(f'Invalid HTML event received: \'{data}\'. HTML event must specify \'id\' field.')
            emit('event_result', {
                'id': event_id,
                'result': 'failed',
                'message': 'HTML event must specify \'id\' field.'
            })
            return False

        # Ignore when disarmed
        if not state.is_armed:
            log.info(f'HTML event \'{event_name}\' ignored. (reason: ICE is disarmed)')
            emit('event_result', {
                'id': event_id,
                'result': 'failed',
                'message': 'ICE is disarmed.'
            })
            return False

        # Broadcast event
        log.info(f'HTML event \'{event_name}\' accepted. Broadcasting event...')

        emit('event_result', {
            'id': event_id,
            'result': 'success',
            'message': 'HTML event accepted and broadcasted.'
        })

        data['eventSource'] = 'html'
        sio_instance.emit('event', data)

        return True

    @sio_instance.on('ping')
    def handle_ping():
        # Update last_seen and alive
        if request.sid in state.connected_clients:
            state.connected_clients[request.sid]['last_seen'] = datetime.datetime.now()
            state.connected_clients[request.sid]['alive'] = True # Mark as alive on ping

        # Build response body using utils functions
        all_client_list_pc = utils.get_connected_client_list('pc', False)
        all_client_list_ha = utils.get_connected_client_list('ha', False)
        all_client_list_html = utils.get_connected_client_list('html', False)

        alive_client_list_pc = utils.get_connected_client_list('pc', True)
        alive_client_list_ha = utils.get_connected_client_list('ha', True)
        alive_client_list_html = utils.get_connected_client_list('html', True)

        emit('pong', {
            'timestamp': datetime.datetime.now().isoformat(),
            'isArmed': state.is_armed,
            'isNormal': state.is_normal,
            'clientList': {
                'pc': all_client_list_pc,
                'ha': all_client_list_ha,
                'html': all_client_list_html
            },
            'aliveClientCount': {
                'pc': len(alive_client_list_pc),
                'ha': len(alive_client_list_ha),
                'html': len(alive_client_list_html)
            }
        })