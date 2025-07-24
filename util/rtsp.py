import cv2
import threading
import time
import base64

class RTSP:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.cap = None
        self.is_streaming = False
        self.frame = None
        self.lock = threading.Lock()

    def connect(self):
        """RTSP 스트림에 연결"""
        try:
            self.cap = cv2.VideoCapture(self.rtsp_url)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            print(f"RTSP 연결 성공")
            return self.cap.isOpened()
        except Exception as e:
            print(f"RTSP 연결 실패: {e}")
            return False

    def start_streaming(self):
        """스트리밍 시작"""
        if not self.connect():
            return False

        self.is_streaming = True
        thread = threading.Thread(target=self._stream_worker)
        thread.daemon = True
        thread.start()
        print(f"RTSP 스트리밍 시작")
        return True

    def stop_streaming(self):
        """스트리밍 중지"""
        print(f"RTSP 스트리밍 중지")
        self.is_streaming = False
        if self.cap:
            self.cap.release()

    def get_frame(self):
        # Encode to JPEG
        _, buffer = cv2.imencode('.jpg', self.frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 70])

        # Base64로 인코딩
        frame_base64 = base64.b64encode(buffer).decode('utf-8')

        return frame_base64

    def _stream_worker(self):
        """스트리밍 워커 스레드"""
        while self.is_streaming and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame

                time.sleep(0.033)  # ~30 FPS
            else:
                print("프레임 읽기 실패")
                break