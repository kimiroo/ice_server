const paramsString = window.location.search;
const searchParams = new URLSearchParams(paramsString);

const wsURL = '';
const clientName = searchParams.get('clientName');

if (!clientName) {
    alert('Client name not set. Redirecting to home...');
    window.location.href = '/';
}

document.addEventListener('DOMContentLoaded', () => {

    // Constants
    const eventTypesToFilter = [
        'onvif'
    ];

    // Elements
    const btnKill = document.getElementById('btnKill');
    const btnArm = document.getElementById('btnArm');
    const btnRecover = document.getElementById('btnRecover');
    const btnToggleFullscreen = document.getElementById('btnToggleFullscreen');

    const videoElem = document.getElementById('video');
    const videoLoadingMessage = document.getElementById('videoLoadingMessage');
    const videoOverlayElem = document.getElementById('videoOverlay');
    const videoOverlayMessage = document.getElementById('videoOverlayMessage');

    const statusConnected = document.getElementById('statusConnected');
    const statusArmed = document.getElementById('statusArmed');
    const statusClientName = document.getElementById('statusClientName');
    const statusCountHTML = document.getElementById('statusCountHTML');
    const statusCountHA = document.getElementById('statusCountHA');
    const statusCountPC = document.getElementById('statusCountPC');
    const statusClientListHTML = document.getElementById('statusClientListHTML');
    const statusClientListHA = document.getElementById('statusClientListHA');
    const statusClientListPC = document.getElementById('statusClientListPC');

    let isArmed = false;
    let isConected = false;
    let heartbeatTimestamp = new Date(0);

    let lastEventID = null;
    let emitedEventList = [];
    let receivedEventList = [];

    let currentEventName = '';
    let currentEventTimestamp = new Date(0);

    let clientListPC = [];
    let clientListHA = [];
    let clientListHTML = [];

    const socket = io({
        transports: ['websocket', 'polling'],
        upgrade: true,
        rememberUpgrade: false,
        timeout: 1000,
        forceNew: true
    });

    function clearOldEvents(eventList) {
        const timeNow = new Date();
        return eventList.filter(event => {
            const timeDiff = timeNow.getTime() - event['timestamp'].getTime();
            return timeDiff < 15 * 1000;
        });
    }

    function handleEvent(eventObj, isIgnored) {
        // ACK Event
        let ackList = [];
        ackList.push(eventObj['id']);
        socket.emit('ack', {
            'id': eventObj['id'],
        });

        lastEventID = eventObj['id'];

        //


        receivedEventList.push(eventObj);

        addLogEntry(`Event: ${eventObj['event']}`, true);
        flash(eventObj['event']);
    }

    function handleInternalEvent(eventObj, isIgnored) {
        //
    }

    function flash(eventName) {
        document.body.classList.add('flash-red');
        videoOverlayElem.classList.add('flash-red')

        setTimeout(() => {
            removeFlash()
        }, 15000);

        showVideoOverlay(`EVENT: ${eventName.toUpperCase()}`);
    }

    function removeFlash() {
        document.body.classList.remove('flash-red');
        videoOverlayElem.classList.remove('flash-red')
    }

    function triggerEvent(eventName) {
        const selectedKillMode = document.querySelector('input[name="killMode"]:checked').value;
        const eventID = crypto.randomUUID();
        const payload = {
            'id': eventID,
            'event': eventName,
            'type': 'user',
            'source': 'html',
            'data': {
                'killMode': selectedKillMode
            }
        }
        socket.emit('event', payload);
        emitedEventList.push({
            'id': eventID,
            'name': eventName,
            'timestamp': new Date()
        });
    }

    function showVideoOverlay(message) {

        videoOverlayMessage.innerText = message;
        videoOverlayElem.style.display = 'block';

        setTimeout(() => {
            videoOverlayMessage.innerText = '';
            videoOverlayElem.style.display = 'none';
        }, 15000);
    }

    function addLogEntry(message, isPriority = false) {
        const logContainer = document.getElementById('logContainer');
        const timestamp = new Date().toISOString().slice(0, 19).replace('T', ' ');

        const logEntry = document.createElement('div');
        logEntry.className = isPriority ? 'log-entry event' : 'log-entry';
        logEntry.textContent = `${timestamp} - ${message}`;

        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function updateElement(element, newContent, isHTML = false) {
        if (!isHTML && element.innerText != newContent) {
            element.innerText = newContent;
        } else if (isHTML && element.innerHTML != newContent) {
            element.innerHTML = newContent;
        }
    }

    function updatePage() {
        // Common elements
        updateElement(statusConnected, isConected ? 'True' : 'False');
        updateElement(statusCountHTML, clientListHTML.length);
        updateElement(statusCountHA, clientListHA.length);
        updateElement(statusCountPC, clientListPC.length);

        function updateClientList(clientList, element) {
            let newContent = '';
            clientList.forEach(client => {
                newContent += `<li><b>${client['name']}</b></li>`;
            });
            if (newContent == '') {
                newContent = '<li><b>🚨 None</b></li>';
            }
            updateElement(element, newContent, true);
        }
        updateClientList(clientListHTML, statusClientListHTML);
        updateClientList(clientListHA, statusClientListHA);
        updateClientList(clientListPC, statusClientListPC);

        if (isArmed) {
            if (document.body.classList.contains('is-disarmed') ||
                !document.body.classList.contains('is-armed')) {
                document.body.classList.remove('is-disarmed');
                document.body.classList.add('is-armed');
            }

            if (btnKill.classList.contains('disabled')) {
                btnKill.classList.remove('disabled');
            }

            updateElement(statusArmed, 'True');
            updateElement(btnArm, '🔌 Disarm ICE');
        } else {
            if (document.body.classList.contains('is-armed') ||
                !document.body.classList.contains('is-disarmed')) {
                document.body.classList.remove('is-armed');
                document.body.classList.add('is-disarmed');
            }

            if (!btnKill.classList.contains('disabled')) {
                btnKill.classList.add('disabled');
            }

            updateElement(statusArmed, 'False');
            updateElement(btnArm, '🚨 Arm ICE');
        }
    }

    function updateHeartbeat() {
        const timeDiff = Date.now() - heartbeatTimestamp.getTime();
        isConected = timeDiff < 1000 && socket.connected; // 1 second

        if (!isConected) {
            // TODO: emit internal event
            updatePage();
        } else {
            // TODO: remove?
        }
    }

    function onDisconnect(event, message) {
        isConected = false;
        updatePage();
        // TODO
        // TODO: emit internal event
    }

    function canShowEvent(eventName) {
        const currentTimestamp = Date.now();
        const timeDiff = currentTimestamp - currentEventTimestamp;

        if (eventName == currentEventName) {
            if (timeDiff > 15 * 1000) {
                return true;
            } else {
                return false;
            }
        } else {
            return true;
        }
    }

    socket.on('connect', () => {
        let payload = {
            'name': clientName,
            'type': 'html'
        }
        if (lastEventID != null) {
            payload['lastEventID'] = lastEventID
        }
        socket.emit('introduce', payload)
    })

    socket.on('event', (data) => {
        handleEvent(data['event'], isIgnored=false);
    });

    socket.on('event_ignored', (data) => {
        handleEvent(data['event'], isIgnored=true);
    });

    socket.on('ping', (data) => {
        socket.emit('get');
    });

    socket.on('get_result', (data) => {
        isArmed = data['isArmed'] == true ? true : false;

        const eventList = data['eventList'];
        const clientList = data['clientList'];
        let newClientListPC = [];
        let newClientListHA = [];
        let newClientListHTML = [];

        clientList.forEach(client => {
            if (client['type'] === 'pc') {
                newClientListPC.push(client);
            } else if (client['type'] === 'ha') {
                newClientListHA.push(client);
            } else if (client['type'] === 'html') {
                newClientListHTML.push(client);
            }
        });
        clientListPC = newClientListPC;
        clientListHA = newClientListHA;
        clientListHTML = newClientListHTML;

        if (eventList.length > 0) {
            addLogEntry(`Detected a delay in processing event: ${eventList.length} events in queue`, false)

            eventList.forEach(event => {
                handleEvent(event, isIgnored=false);
            });
        }

        socket.emit('pong');

        // Update heartbeat
        heartbeatTimestamp = new Date();
        updateHeartbeat();

        // Connected client count check
        if (clientListPC.length == 0 ||
            clientListHA.length == 0 ||
            clientListHTML.length == 0) {
            // canShowEvent('zero_client')
            // TODO: emit internal event
        } else {
            // Remove flash?
        }

        updatePage();
    });

    socket.on("connect_error", (error) => {
        onDisconnect("connect_error", error);
    });

    socket.on("disconnect", (reason) => {
        onDisconnect("disconnect", reason);
    });

    btnKill.addEventListener('click', () => {
        triggerEvent('kill');
    });

    btnArm.addEventListener('click', () => {
        socket.emit('set_armed', {'armed': !isArmed});
    });

    btnRecover.addEventListener('click', () => {
        triggerEvent('recover');
    });

    btnToggleFullscreen.addEventListener('click', () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen()
        } else {
            if (document.exitFullscreen) {
            document.exitFullscreen()
            }
        }
    });

    // WebRTC
    async function PeerConnection(media) {
        const pc = new RTCPeerConnection({
            iceServers: [{urls: 'stun:stun.l.google.com:19302'}]
        });

        const localTracks = [];

        if (/camera|microphone/.test(media)) {
            const tracks = await getMediaTracks('user', {
                video: media.indexOf('camera') >= 0,
                audio: media.indexOf('microphone') >= 0,
            });
            tracks.forEach(track => {
                pc.addTransceiver(track, {direction: 'sendonly'});
                if (track.kind === 'video') localTracks.push(track);
            });
        }

        if (media.indexOf('display') >= 0) {
            const tracks = await getMediaTracks('display', {
                video: true,
                audio: media.indexOf('speaker') >= 0,
            });
            tracks.forEach(track => {
                pc.addTransceiver(track, {direction: 'sendonly'});
                if (track.kind === 'video') localTracks.push(track);
            });
        }

        if (/video|audio/.test(media)) {
            const tracks = ['video', 'audio']
                .filter(kind => media.indexOf(kind) >= 0)
                .map(kind => pc.addTransceiver(kind, {direction: 'recvonly'}).receiver.track);
            localTracks.push(...tracks);
        }

        videoElem.srcObject = new MediaStream(localTracks);

        return pc;
    }

    async function getMediaTracks(media, constraints) {
        try {
            const stream = media === 'user'
                ? await navigator.mediaDevices.getUserMedia(constraints)
                : await navigator.mediaDevices.getDisplayMedia(constraints);
            return stream.getTracks();
        } catch (e) {
            console.warn(e);
            return [];
        }
    }

    async function connect(media) {
        //const baseUrl = 'ws://10.5.47.10:1984/';
        //const pc = await PeerConnection(media);
        //const url = new URL('api/ws' + location.search, baseUrl);
        //console.log(url);
        //console.log(url.toString().substring(4));
        //const ws = new WebSocket('ws' + url.toString().substring(4));

        const pc = await PeerConnection(media);
        //const go2rtcServerUrl = 'wss://ice.darak.cc'; // CHANGE THIS TO YOUR GO2RTC SERVER
        const go2rtcServerUrl = 'ws://10.5.47.10:1984'; // CHANGE THIS TO YOUR GO2RTC SERVER
        const ws = new WebSocket(`${go2rtcServerUrl}/api/ws?src=tapo_c100&mode=webrtc`);

        ws.addEventListener('open', () => {
            pc.addEventListener('icecandidate', ev => {
                if (!ev.candidate) return;
                const msg = {type: 'webrtc/candidate', value: ev.candidate.candidate};
                ws.send(JSON.stringify(msg));
            });

            pc.createOffer().then(offer => pc.setLocalDescription(offer)).then(() => {
                const msg = {type: 'webrtc/offer', value: pc.localDescription.sdp};
                ws.send(JSON.stringify(msg));
            });
        });

        ws.addEventListener('message', ev => {
            const msg = JSON.parse(ev.data);
            if (msg.type === 'webrtc/candidate') {
                pc.addIceCandidate({candidate: msg.value, sdpMid: '0'});
            } else if (msg.type === 'webrtc/answer') {
                pc.setRemoteDescription({type: 'answer', sdp: msg.value});
            }
        });
    }

    // Main logic

    statusClientName.innerText = clientName;

    setInterval(() => {
        updateHeartbeat();

        function clearOldEvents(eventList) {
            const timeNow = new Date();
            return eventList.filter(event => {
                const timeEvent = new Date(event['timestamp']);
                const timeDiff = timeNow.getTime() - timeEvent.getTime();
                return timeDiff < 15 * 1000;
            });
        }
        emitedEventList = clearOldEvents(emitedEventList);
        receivedEventList = clearOldEvents(receivedEventList);

        updatePage();

        if (!socket.connected) {
            console.log('connecting');
            socket.connect();
        }
    }, 100);

    connect('video+audio');
    videoElem.style.display = 'block';
    videoLoadingMessage.style.display = 'none';
})