import uuid
import logging
from flask import request
from flask_socketio import SocketIO, emit, disconnect

import utils.state as state
import utils.utils as utils
from utils.event_handler import EventHandler
from objects.ice_client import ICEClient
from objects.ice_event import ICEEvent
from objects.ice_queue import ICEEventQueue

log = logging.getLogger(__name__)

CLIENT_TYPES_TO_TRACK = ['pc', 'ha', 'html']

def register_socketio(socketio_instance: SocketIO,
                      event_queue_instance: ICEEventQueue,
                      event_handler_instance: EventHandler):
    """
    Registers all Socket.IO event handlers with the given SocketIO instance.
    """

    @socketio_instance.on('connect')
    def handle_connect():
        try:
            client = None
            headers = dict(request.headers)
            client_type, client_name = utils.identify_client(headers, request.sid)

            log.info(f'Client connecting - Type: {client_type}, Name: {client_name}, SID: {request.sid}')

            if client_type == 'pc' or client_type == 'ha' or client_type == 'test':
                if not client_name:
                    log.warning(f'{client_type.upper()} client {request.sid} connected without client_name')
                    emit('error', {'message': f'client name is required for {client_type.upper()} clients'})
                    return False

            else:
                log.warning(f'Unknown client type for SID: {request.sid}')
                emit('error', {'message': 'Unknown client type'})
                return False

            if client_type in CLIENT_TYPES_TO_TRACK:
                client = event_queue_instance.add_client(request.sid, client_name, client_type)

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
                    event_data=client.to_dict(simplified=True, json_friendly=True)
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
            client = event_queue_instance.get_client(request.sid)

            if client is None:
                log.debug(f"Disconnected client SID {request.sid} not found in connected clients list.")
                return

            log.info(f'Client disconnecting - Type: {client.type}, Name: {client.name}, SID: {request.sid}')

            event = ICEEvent(
                event_id=uuid.uuid4(),
                event_name='disconnected',
                event_type='client',
                event_source='server',
                event_data={
                    'client': client.to_dict(simplified=True, json_friendly=True)
                }
            )
            event_handler_instance.broadcast(event)

            client = None
            event_queue_instance.remove_client(request.sid)
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
                return

            if not event_id:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'id\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'id\' field.'
                })
                return

            if not event_type:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'type\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'type\' field.'
                })
                return

            if not event_source:
                log.error(f'Invalid event received: \'{data}\'. Event must specify \'source\' field.')
                emit('event_result', {
                    'id': event_id,
                    'result': 'failed',
                    'message': 'Event must specify \'source\' field.'
                })
                return

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
            client = event_queue_instance.get_client(request.sid)
            if client is None:
                emit('pong', {
                    'result': 'failed',
                    'reason': 'disconnected'
                })
                disconnect()
                return

            event_queue_instance.update_last_seen(request.sid)
            lookup_result, event_queue = event_queue_instance.get_events(request.sid)

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
            client = event_queue_instance.get_client(request.sid)
            if client is None:
                emit('ack_result', {
                    'result': 'failed',
                    'reason': 'disconnected'
                })
                disconnect()

            event_queue_instance.update_last_seen(request.sid)

            # ACK events
            ack_result = event_queue_instance.ack_events(request.sid, event_id_list)

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
            client = event_queue_instance.get_client(request.sid)

            if client is None or last_fetched_id is None:
                log.error(f'Failed to get client info or last fetched event id.')
                return

            event_queue_instance.restore_queue(request.sid, last_fetched_id)

        except Exception as e:
            log.error(f'Failed to restore event queue for client \'{request.sid}\': {e}')