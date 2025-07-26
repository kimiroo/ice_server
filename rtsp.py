import cv2
import threading
import base64
import eventlet
import logging

class RTSP:
    def __init__(self, rtsp_url):
        self._rtsp_url = rtsp_url
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._is_streaming = False
        self.log = logging.getLogger(__name__)

    def connect(self):
        """RTSP 스트림에 연결"""
        try:
            self._cap = cv2.VideoCapture(self._rtsp_url)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.log.info(f"RTSP 연결 성공")
            return self._cap.isOpened()
        except Exception as e:
            self.log.error(f"RTSP 연결 실패: {e}")
            return False

    def start_streaming(self):
        """스트리밍 시작"""
        if not self.connect():
            return False

        self._is_streaming = True

        eventlet.spawn(self._stream_worker) # 스트림 워커 시작 (eventlet)

        print(f"RTSP 스트리밍 시작")
        return True

    def stop_streaming(self):
        """스트리밍 중지"""        
        print(f"RTSP 스트리밍 중지")
        self._is_streaming = False
        
    def get_frame(self):
        """최신 프레임을 JPEG로 인코딩하여 반환"""
        with self._lock:
            if self._frame is None:
                return None

            # JPEG로 인코딩
            _, buffer = cv2.imencode('.jpg', self._frame,
                            [cv2.IMWRITE_JPEG_QUALITY, 70])

        # Encode to Base64
        frame_base64 = base64.b64encode(buffer).decode('utf-8')

        return frame_base64

    def is_streaming(self):
        return self._is_streaming

    def is_open(self):
        if self._cap is not None:
            return self._cap.isOpened()
        else:
            return False

    def _stream_worker(self):
        """스트리밍 워커 스레드"""
        try:
            while self._is_streaming and self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    with self._lock:
                        self._frame = frame # 최신 프레임 업데이트

                else:
                    print("프레임 읽기 실패")
                eventlet.sleep(0.0333333333333333) # ~30 FPS
                
        except Exception as e:
            with self._lock:
                if self._cap:
                    try:
                        self._cap.release()
                    except Exception as release_e:
                        print(f"Error releasing capture: {release_e}")
                    self._cap = None