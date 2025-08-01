import logging
import eventlet
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

import test_state as state
from ice_queue import ICEEventQueue

log = logging.getLogger(__name__)

def register_api_routes(flask_instance: Flask,
                        socketio_instance: SocketIO,
                        event_queue_instance: ICEEventQueue):
    """Registers all HTTP API routes with the given Flask app and SocketIO instances."""

    @flask_instance.before_request
    def before_request():
        if request.path.startswith('/socket.io/'):
            pass # Ignore http get/post request on ws endpoint

    @flask_instance.route('/')
    def index():
        return render_template('index.html')

    @flask_instance.route('/api/v1/arm/activate', methods=['POST'])
    def arm_activate():
        state.is_armed = True # Update state.is_armed

        log.info(f"System armed. is_armed: {state.is_armed}")

        # notify armed state to all clients
        socketio_instance.emit('ice_status', {
            'isArmed': state.is_armed
        })

        return jsonify({'isArmed': state.is_armed})

    @flask_instance.route('/api/v1/arm/deactivate', methods=['POST'])
    def arm_deactivate():
        state.is_armed = False # Update state.is_armed

        log.info(f"System disarmed. is_armed: {state.is_armed}")

        # notify armed state to all clients
        socketio_instance.emit('ice_status', {
            'isArmed': state.is_armed
        })

        return jsonify({'isArmed': state.is_armed})

    @flask_instance.route('/api/v1/arm/status', methods=['GET'])
    def get_arm_status():
        return jsonify({'isArmed': state.is_armed})

    @flask_instance.route('/api/v1/status', methods=['GET'])
    def get_overall_status():
        client_list_pc = event_queue_instance.get_client_list('pc', is_alive=False, json_friendly=True)
        client_list_ha = event_queue_instance.get_client_list('ha', is_alive=False, json_friendly=True)
        client_list_html = event_queue_instance.get_client_list('html', is_alive=False, json_friendly=True)

        alive_client_list_pc = event_queue_instance.get_client_list('pc', is_alive=True, json_friendly=True)
        alive_client_list_ha = event_queue_instance.get_client_list('ha', is_alive=True, json_friendly=True)
        alive_client_list_html = event_queue_instance.get_client_list('html', is_alive=True, json_friendly=True)

        return jsonify({
            'isArmed': state.is_armed,
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
        })

    @flask_instance.route('/api/v1/connected-clients/<client_type>', methods=['GET'])
    def get_connected_clients_api(client_type):
        client_list = event_queue_instance.get_client_list(client_type, is_alive=False, json_friendly=True)
        alive_client_list = event_queue_instance.get_client_list(client_type, is_alive=True, json_friendly=True)

        return jsonify({
            'clientList': client_list,
            'aliveClientList': alive_client_list
        })