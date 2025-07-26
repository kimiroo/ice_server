import logging
import eventlet
from flask import render_template, jsonify, request

import state
import utils
from rtsp import RTSP

log = logging.getLogger(__name__)

def register_api_routes(app_instance, sio_instance, rtsp_instance: RTSP):
    """Registers all HTTP API routes with the given Flask app and SocketIO instances."""

    @app_instance.before_request
    def before_request():
        if request.path.startswith('/socket.io/'):
            pass # Ignore http get/post request on ws endpoint

    @app_instance.route('/')
    def index():
        return render_template('index.html')

    @app_instance.route('/api/v1/arm/activate', methods=['POST'])
    def arm_activate():
        state.is_armed = True # Update state.is_armed

        log.info(f"System armed. is_armed: {state.is_armed}")

        # notify armed state to all clients
        sio_instance.emit('ice_status', {
            'isArmed': state.is_armed
        })

        # Start RTSP stream
        eventlet.spawn(rtsp_instance.start_streaming)

        return jsonify({'isArmed': state.is_armed})

    @app_instance.route('/api/v1/arm/deactivate', methods=['POST'])
    def arm_deactivate():
        state.is_armed = False # Update state.is_armed

        log.info(f"System disarmed. is_armed: {state.is_armed}")

        # notify armed state to all clients
        sio_instance.emit('ice_status', {
            'isArmed': state.is_armed
        })

        # End RTSP stream
        eventlet.spawn(rtsp_instance.stop_streaming)

        return jsonify({'isArmed': state.is_armed})

    @app_instance.route('/api/v1/arm/status', methods=['GET'])
    def get_arm_status():
        return jsonify({'isArmed': state.is_armed})

    @app_instance.route('/api/v1/ice/status', methods=['GET'])
    def get_ice_status():
        return jsonify({'isNormal': state.is_normal})

    @app_instance.route('/api/v1/status', methods=['GET'])
    def get_overall_status():
        return jsonify({
            'isArmed': state.is_armed,
            'isNormal': state.is_normal
        })

    @app_instance.route('/connected-clients/<client_type>', methods=['GET'])
    def get_connected_clients_api(client_type):
        all_client_list = utils.get_connected_client_list(client_type, False)
        alive_client_list = utils.get_connected_client_list(client_type, True)

        return jsonify({
            'clients': all_client_list,
            'aliveClientCount': len(alive_client_list)
        })