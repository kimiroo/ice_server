import cv2
import threading
import time
import base64

class RTSP:
    def __init__(self, rtsp_url):
        self._rtsp_url = rtsp_url
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._is_streaming = False

    def connect(self):
        """RTSP 스트림에 연결"""
        try:
            self._cap = cv2.VideoCapture(self._rtsp_url)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cap.set(cv2.CAP_PROP_FPS, 30)
            print(f"RTSP 연결 성공")
            return self._cap.isOpened()
        except Exception as e:
            print(f"RTSP 연결 실패: {e}")
            return False

    def start_streaming(self):
        """스트리밍 시작"""
        if not self.connect():
            return False

        self._is_streaming = True
        thread = threading.Thread(target=self._stream_worker)
        thread.daemon = True
        thread.start()
        print(f"RTSP 스트리밍 시작")
        return True

    def stop_streaming(self):
        """스트리밍 중지"""
        print(f"RTSP 스트리밍 중지")
        self._is_streaming = False
        if self._cap:
            self._cap.release()

    def get_frame(self):
        # Encode to JPEG
        _, buffer = cv2.imencode('.jpg', self._frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 70])

        # Encode to Base64
        frame_base64 = base64.b64encode(buffer).decode('utf-8')

        return frame_base64

    def is_streaming(self):
        return self._is_streaming

    def is_open(self):
        if self._cap:
            return self._cap.isOpened()
        else:
            return False

    def _stream_worker(self):
        """스트리밍 워커 스레드"""
        while self._is_streaming and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame

                time.sleep(0.0333333333333333) # ~30 FPS
            else:
                print("프레임 읽기 실패")
                break