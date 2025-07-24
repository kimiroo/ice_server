from flask import Flask, render_template, Response, jsonify
from flask_socketio import SocketIO, emit
import cv2
import base64
import threading
import time
import numpy as np
from datetime import datetime
import json
import logging

from util.rtsp import RTSP

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app,
                   cors_allowed_origins="*",
                   logger=False,
                   engineio_logger=False,
                   async_mode='threading')


# 전역 변수들
connected_clients = set()
rtsp_url = "rtsp://tapo_cam:zz%6k5CWYXc0tpTSqwS*qbgYD6!$axmK@10.5.21.10:554/stream1"

# Init
rtsp = RTSP(rtsp_url)
rtsp.start_streaming()

@socketio.on('connect')
def handle_connect():
    from flask import request
    connected_clients.add(request.sid)
    print(f'클라이언트 연결됨: {request.sid}')
    print(f'총 연결된 클라이언트: {len(connected_clients)}')
    emit('status', {'message': '서버에 연결되었습니다'})

@socketio.on('disconnect')
def handle_disconnect():
    from flask import request
    connected_clients.discard(request.sid)
    print(f'클라이언트 연결 해제됨: {request.sid}')
    print(f'총 연결된 클라이언트: {len(connected_clients)}')

@socketio.on('ping')
def handle_ping():
    print('클라이언트로부터 ping 받음')
    emit('pong', {'timestamp': datetime.now().isoformat()})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_stream', methods=['POST'])
def start_stream():

    def send_frame():
        try:
            socketio.emit('video_frame', {
                'frame': rtsp.get_frame(),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            print(f"프레임 전송 실패: {e}")

    def stream_worker():
        while True:
            send_frame()
            time.sleep(0.033)


    try:
        thread = threading.Thread(target=stream_worker)
        thread.daemon = True
        thread.start()

        message = '스트리밍 시작됨'
        print(message)

        return jsonify({
            'success': True,
            'message': message
        })
    except Exception as e:
        error_msg = f'오류: {str(e)}'
        print(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': error_msg
        })

@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    global streamer

    try:
        if streamer:
            streamer.stop_streaming()
            streamer = None

        return jsonify({
            'success': True,
            'message': '스트리밍 중지됨'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'오류: {str(e)}'
        })

if __name__ == '__main__':

    # eventlet 사용으로 변경
    socketio.run(app,
                host='0.0.0.0',
                port=5000,
                debug=True,
                use_reloader=False)  # 디버그 모드에서 reloader 비활성화