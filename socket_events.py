import uuid
import logging
from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

import utils.state as state
import utils.utils as utils
from utils.event_handler import EventHandler
from objects.ice_client import ICEClient
from objects.ice_event import ICEEvent
from objects.ice_queue import ICEEventQueue
from objects.sid_manager import SIDManager, SIDObject

log = logging.getLogger(__name__)

ROOM_HTML = state.ROOM_HTML
ROOM_PC = state.ROOM_PC
ROOM_HA = state.ROOM_HA

CLIENT_TYPES_TO_TRACK = ['pc', 'ha', 'html']

def register_socketio(socketio_instance: SocketIO,
                      event_queue_instance: ICEEventQueue,
                      sid_manager_instance: SIDManager,
                      event_handler_instance: EventHandler):
    """
    Registers all Socket.IO event handlers with the given SocketIO instance.
    """

    @socketio_instance.on('connect')
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

            sid_manager_instance.add_sid(request.sid, client_name, client_type)
            if client_type in CLIENT_TYPES_TO_TRACK:
                event_queue_instance.add_client(client_name, client_type)

            emit('connected', {
                'status': 'success',
                'clientName': client_name,
                'clientType': client_type,
                'sid': request.sid
            })

            if client_type in CLIENT_TYPES_TO_TRACK:
                ### Broadcast
                event = ICEEvent(
                    event_id=uuid.uuid4(),
                    event_name='connected',
                    event_type='client',
                    event_source='server',
                    event_data={
                        'client': {
                            'clientName': client_name,
                            'clientType': client_type,
                            'sid': request.sid
                        }
                    }
                )
                event_handler_instance.broadcast(event)

        except Exception as e:
            log.error(f'Error in handle_connect: {e}')
            emit('error', {
                'result': 'failed',
                'message': f'Connection failed: {e}'
            })
            return False

    @socketio_instance.on('disconnect')
    def handle_disconnect():
        try:
            if sid_manager_instance.is_test_client(request.sid):
                sid_manager_instance.remove_sid(request.sid)
                return

            sid_obj: SIDObject = sid_manager_instance.get_sid_object(request.sid)
            client_obj: ICEClient = None
            client_name: str = None
            client_type: str = None

            if sid_obj is not None:
                try:
                    client_name = sid_obj.client_name
                    client_obj = event_queue_instance.get_client(request.sid)
                    client_type = client_obj.type
                    sid_manager_instance.remove_sid(request.sid)
                except:
                    pass

            sid_list = sid_manager_instance.get_sid_list(client_name, False)

            if len(sid_list) == 0:
                ### Broadcast
                event = ICEEvent(
                    event_id=uuid.uuid4(),
                    event_name='disconnected',
                    event_type='client',
                    event_source='server',
                    event_data={
                        'client': {
                            'clientName': client_name,
                            'clientType': client_type,
                            'sid': request.sid
                        }
                    }
                )
                event_handler_instance.broadcast(event)
            else:
                log.warning(f"Disconnected client SID {request.sid} not found in connected_clients.")
        except Exception as e:
            log.error(f'Error in handle_disconnect: {e}')

    @socketio_instance.on('event')
    def handle_event(data = {}):
        try:
            event_id = data.get('id', None)
            event_name = data.get('event', None)
            event_type = data.get('type', None)
            event_source = data.get('source', None)
            event_data = data.get('data', None)

            # Message structure check
            if not event_name:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'event\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'event\' field.'
                })
                return False

            if not event_id:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'id\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'id\' field.'
                })
                return False

            if not event_type:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'type\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'type\' field.'
                })
                return False

            if not event_source:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'source\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'source\' field.'
                })
                return False

            event = ICEEvent(
                event_id=event_id,
                event_name=event_name,
                event_type=event_type,
                event_source=event_source,
                event_data=event_data
            )

            result, message = event_handler_instance.broadcast(event)

            if result == 'ignored':
                emit('event_result', {
                    'id': event_id,
                    'result': 'success',
                    'message': 'Event ignored. (reason: previous event still valid)'
                })
                return
            elif result == 'broadcasted':
                emit('event_result', {
                    'id': event_id,
                    'result': 'success',
                    'message': 'Event accepted and broadcasted.'
                })
            elif result == 'unarmed':
                emit('event_result', {
                    'id': event_id,
                    'result': 'success',
                    'message': 'Event ignored. (reason: ICE is disarmed)'
                })
            else:
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': f'Failed to process event: {message if message is not None or message != '' else 'No error message'}'
                })

        except Exception as e:
            log.error(f'Failed to process event \'{event_name}\': {e}')
            emit('event_result', {
                'id': event_id,
                'result': 'failed',
                'message': f'Failed to process event: {e}'
            })
            return False

    @socketio_instance.on('ping')
    def handle_ping():
        try:
            # Update last_seen and alive
            sid_obj = sid_manager_instance.get_sid_object(request.sid)
            if sid_obj is None:
                emit('pong', {
                    'result': 'failed',
                    'reason': 'disconnected'
                })
                disconnect()
                return

            client_name = sid_obj.client_name
            sid_manager_instance.update_last_seen(request.sid)
            event_queue_instance.update_last_seen(client_name)

            lookup_result, event_queue = event_queue_instance.get_events(client_name)

            event_queue_list = []
            if lookup_result:
                for event in event_queue:
                    event_queue_list.append(event.to_dict(json_friendly=True))

            result = 'success' if lookup_result else 'failed'

            emit('pong', {
                'result': result,
                'isArmed': state.is_armed,
                'events': event_queue_list
            })

        except Exception as e:
            log.error(f'Error while handling PING: {e}')
            emit('pong', {
                'result': 'failed'
            })

    @socketio_instance.on('ack')
    def handle_ack(data = {}):
        try:
            event_id_list = data.get('ackList', [])

            # Update last_seen and alive
            sid_obj = sid_manager_instance.get_sid_object(request.sid)
            if sid_obj is None:
                emit('ack_result', {
                    'result': 'failed',
                    'reason': 'disconnected'
                })
                disconnect()

            client_name = sid_obj.client_name
            sid_manager_instance.update_last_seen(request.sid)
            event_queue_instance.update_last_seen(client_name)

            # ACK events
            ack_result = event_queue_instance.ack_events(client_name, event_id_list)

            result = 'success' if ack_result else 'failed'

            emit('ack_result', {
                'result': result
            })

        except Exception as e:
            emit('ack_result', {
                'result': 'failed',
                'message': f'Error while handling \'ack\': {e}'
            })

    @socketio_instance.on('get')
    def handle_get(data = {}):
        try:
            resource_name = data.get('resource', None)

            if resource_name == 'clients':
                client_list_pc = event_queue_instance.get_client_list('pc', is_alive=False, json_friendly=True)
                client_list_ha = event_queue_instance.get_client_list('ha', is_alive=False, json_friendly=True)
                client_list_html = event_queue_instance.get_client_list('html', is_alive=False, json_friendly=True)

                alive_client_list_pc = event_queue_instance.get_client_list('pc', is_alive=True, json_friendly=True)
                alive_client_list_ha = event_queue_instance.get_client_list('ha', is_alive=True, json_friendly=True)
                alive_client_list_html = event_queue_instance.get_client_list('html', is_alive=True, json_friendly=True)

                emit('get_result', {
                    'result': 'success',
                    'resource': 'clients',
                    'data': {
                        'clientList': {
                            'pc': client_list_pc,
                            'ha': client_list_ha,
                            'html': client_list_html
                        },
                        'aliveClientList': {
                            'pc': alive_client_list_pc,
                            'ha': alive_client_list_ha,
                            'html': alive_client_list_html
                        }
                    }
                })

            else:
                emit('get_result', {
                    'result': 'failed',
                    'message': f'Unknown resource \'{resource_name}\''
                })

        except Exception as e:
            emit('get_result', {
                'result': 'failed',
                'message': f'Error while handling \'get\': {e}'
            })

    @socketio_instance.on('restore_queue')
    def handle_restore_queue(data):
        try:
            last_fetched_id = data.get('id', None)
            sid_object = sid_manager_instance.get_sid_object(request.sid)
            client_name = None

            try:
                client_name = sid_object.client_name
            except:
                pass

            if client_name is not None and last_fetched_id is not None:
                log.debug(f'Restoring event queue of client \'{client_name}\' with event id \'{last_fetched_id}\'...')
                event_queue_instance.restore_queue(client_name, last_fetched_id)
            else:
                log.error(f'Failed to get client name or last fetched event id.')

        except Exception as e:
            log.error(f'Failed to restore event queue for client \'{client_name}\': {e}')