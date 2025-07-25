import asyncio
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from test_stream import GstVideoStreamTrack

pcs = set()

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("iceconnectionstatechange")
    async def on_ice():
        print("ICE:", pc.iceConnectionState)
        if pc.iceConnectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    rtsp_uri = 'rtsp://10.5.21.10:554/stream1'
    username = 'tapo_cam'
    password = 'zz%6k5CWYXc0tpTSqwS*qbgYD6!$axmK'
    pipeline_str = (
        f'rtspsrc location={rtsp_uri} latency=0 user-id={username} user-pw={password} ! '
        'rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! '
        'video/x-raw, format=RGB ! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false'
    )

    track = GstVideoStreamTrack(pipeline_str)
    pc.addTrack(track)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    })

async def on_shutdown(app):
    await asyncio.gather(*[pc.close() for pc in pcs])
    pcs.clear()

async def index(request):
    return web.FileResponse('./index.html')

app = web.Application()
app.router.add_post("/offer", offer)
app.router.add_get('/', index)
app.on_shutdown.append(on_shutdown)

web.run_app(app, port=8080)
