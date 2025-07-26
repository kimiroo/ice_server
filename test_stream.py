from aiortc import VideoStreamTrack
from gi.repository import Gst, GLib
import threading
import av
import asyncio

Gst.init(None)

class GstVideoStreamTrack(VideoStreamTrack):
    def __init__(self, pipeline_str):
        super().__init__()
        self.loop = GLib.MainLoop()
        self.buffer = None
        self.lock = threading.Lock()

        self.pipeline = Gst.parse_launch(pipeline_str)
        self.appsink = self.pipeline.get_by_name("sink")
        self.appsink.connect("new-sample", self.on_new_sample)

        threading.Thread(target=self._run_loop, daemon=True).start()
        self.pipeline.set_state(Gst.State.PLAYING)

    def _run_loop(self):
        self.loop.run()

    def on_new_sample(self, sink):
        sample = sink.emit("pull-sample")
        buf = sample.get_buffer()
        caps = sample.get_caps()
        with self.lock:
            self.buffer = (buf, caps)
        return Gst.FlowReturn.OK

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        while True:
            await asyncio.sleep(0.01)
            with self.lock:
                if self.buffer:
                    buf, caps = self.buffer
                    self.buffer = None
                    break

        # Extract width/height and format
        structure = caps.get_structure(0)
        width = structure.get_value('width')
        height = structure.get_value('height')

        # Extract raw bytes
        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            raise Exception("Failed to map buffer")

        frame = av.VideoFrame.from_ndarray(
            memoryview(map_info.data).tobytes(),  # raw bytes
            format='yuv420p',
            width=width,
            height=height
        )
        frame.pts = pts
        frame.time_base = time_base
        buf.unmap(map_info)
        return frame
