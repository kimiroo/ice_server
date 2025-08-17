const paramsString = window.location.search;
const searchParams = new URLSearchParams(paramsString);

const wsURL = '';
const clientName = searchParams.get('clientName');

if (!clientName) {
    alert('Client name not set. Redirecting to home...');
    window.location.href = '/';
}

document.addEventListener('DOMContentLoaded', () => {

    // Elements
    const btnKill = document.getElementById('btnKill');
    const btnIgnore = document.getElementById('btnIgnore');
    const btnArm = document.getElementById('btnArm');
    const btnRecover = document.getElementById('btnRecover');
    const btnToggleFullscreen = document.getElementById('btnToggleFullscreen');

    const videoElem = document.getElementById('video');
    const videoLoadingMessage = document.getElementById('videoLoadingMessage');
    const videoOverlayElem = document.getElementById('videoOverlay');
    const videoOverlayMessage = document.getElementById('videoOverlayMessage');

    const statusConnected = document.getElementById('statusConnected');
    const statusCamera = document.getElementById('statusCamera');
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
    let cameraState = null;

    let lastEventID = null;
    let emitedEventList = [];
    let receivedEventList = [];
    let flashEventSource = null;

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

    function capitalizeFirstLetter(str) {
    if (str.length === 0) {
        return ""; // Handle empty strings
    }
    return str.charAt(0).toUpperCase() + str.slice(1);
    }

    function isPreviousEventValid(eventType, eventName = null) {
        for (const event of receivedEventList) {
            const timeNow = new Date();
            const timeEvent = new Date(event['timestamp']);
            const timeDiff = timeNow.getTime() - timeEvent.getTime();

            if (timeDiff < 15 * 1000 && event['type'] === eventType) {
                if (eventName === null || event['event'] === eventName) {
                    return true;
                }
            }
        }
        return false;
    }

    function isEmitedEvent(eventID) {
        for (const event of emitedEventList) {
            if (event['id'] === eventID) {
                return true;
            }
        }
        return false;
    }

    function handleEvent(eventObj, isIgnored) {
        // ACK Event
        let ackList = [];
        ackList.push(eventObj['id']);
        socket.emit('ack', {
            'id': eventObj['id'],
        });

        lastEventID = eventObj['id'];

        if (isIgnored) {
            if (eventObj['type'] === 'onvif') {
                addLogEntry(`IGNORED_ONVIF: ${capitalizeFirstLetter(eventObj['event'])} ignored.`);
            } else if (eventObj['type'] === 'user') {
                if (eventObj['event'] === 'kill') {
                    addLogEntry(`IGNORED_USER: User broadcasted event '${eventObj['event'].toUpperCase()}' with mode '${eventObj['data']['killMode'].toUpperCase()}' ignored.`);
                } else {
                    addLogEntry(`IGNORED_USER: User broadcasted event '${eventObj['event'].toUpperCase()}'.`);
                }
            } else if (eventObj['type'] === 'client') {
                addLogEntry(`IGNORED_CLIENT: Client '${eventObj['data']['client']['name']}' ${eventObj['event']}.`)
            }
        } else {
            if (eventObj['type'] === 'onvif' && !isPreviousEventValid('onvif')) {
                receivedEventList.push(eventObj);
                addLogEntry(`ONVIF: ${capitalizeFirstLetter(eventObj['event'])} Detected!`, true);
                flash(`${eventObj['type']}_${eventObj['event']}`);
                showVideoOverlay(`${eventObj['event'].toUpperCase()} DETECTED!`);

            } else if (eventObj['type'] === 'user' && !isEmitedEvent(eventObj['id'])) {
                receivedEventList.push(eventObj);
                if (eventObj['event'] === 'kill') {
                    addLogEntry(`USER: User broadcasted event '${eventObj['event'].toUpperCase()}' with mode '${eventObj['data']['killMode'].toUpperCase()}'.`, true);
                } else {
                    addLogEntry(`USER: User broadcasted event '${eventObj['event'].toUpperCase()}'.`, true);
                }

            } else if (eventObj['type'] === 'client') {
                receivedEventList.push(eventObj);
                if (eventObj['event'] === 'connected') {
                    addLogEntry(`CLIENT: Client '${eventObj['data']['client']['name']}' ${eventObj['event']}.`);
                } else {
                    addLogEntry(`CLIENT: Client '${eventObj['data']['client']['name']}' ${eventObj['event']}.`, true);
                    flash(`${eventObj['type']}_${eventObj['event']}`);
                    showVideoOverlay(`CLIENT '${eventObj['data']['client']['name']}' DISCONNECTED!`);
                }
            }
        }
    }

    function handleInternalEvent(eventObj) {
        if (!isPreviousEventValid(eventObj['type'], eventObj['event'])) {
            receivedEventList.push(eventObj);
            if (eventObj['event'] === 'zero_client') {
                addLogEntry(`CLIENT: Zero client detected: PC: ${clientListPC.length}, HA: ${clientListHA.length}, HTML: ${clientListHTML.length}`, true);
                showVideoOverlay(`ZERO CLIENT DETECTED!`);
            } else if (eventObj['event'] === 'disconnected') {
                addLogEntry(`CONNECTION: Connection to server lost.`, true);
                showVideoOverlay(`CONNECTION LOST!`);
            }
            flash(`${eventObj['type']}_${eventObj['event']}`);
        }
    }

    function onCameraStateChanged(state) {
        console.log('Camera state changed:', state);
        statusCamera.innerText = state;
        if (state === 'connected') {
            videoElem.style.display = 'block';
            videoLoadingMessage.style.display = 'none';
        } else {
            if (state === 'disconnected' || state === 'failed') {
                videoLoadingMessage.innerText = '📹 Camera Feed Disconnected. Retrying...';
            }
            videoElem.style.display = 'none';
            videoLoadingMessage.style.display = 'block';
        }
    }

    function flash(eventName) {
        document.body.classList.add('flash-red');
        videoOverlayElem.classList.add('flash-red');
        flashEventSource = eventName;

        setTimeout(() => {
            removeFlash()
        }, 15000);
    }

    function removeFlash() {
        document.body.classList.remove('flash-red');
        videoOverlayElem.classList.remove('flash-red');
        flashEventSource = null;
    }

    function triggerEvent(eventName, isKill) {
        if (!isArmed) {
            alert('ICE isn\'t armed.');
            return;
        }
        const selectedKillMode = document.querySelector('input[name="killMode"]:checked').value;
        const eventID = generateUUID();
        let payload = {
            'id': eventID,
            'event': eventName,
            'type': 'user',
            'source': 'html',
            'data': {}
        }
        if (isKill) {
            payload['data']['killMode'] = selectedKillMode;
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

        // Create a new Date object representing the current moment.
        const date = new Date();

        // Get year, month, day, hours, minutes, and seconds from the date object.
        // The methods used (e.g., getFullYear()) automatically return values based on the local timezone.
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0'); // Month is zero-indexed, so add 1.
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        // Combine the parts into the desired format and return the string.
        const timestamp = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;

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

        function createClientList(clientList) {
            let newContent = '';
            clientList.forEach(client => {
                if (newContent === '') {
                    newContent += `${client['name']}`;
                } else {
                    newContent += `, ${client['name']}`
                }
            })
            if (newContent === '') {
                newContent = '🚨None🚨';
            }
            return `( ${newContent} )`
        }

        // Common elements
        updateElement(statusConnected, isConected ? 'True' : 'False');
        updateElement(statusCountHTML, `<b>${clientListHTML.length}</b>&nbsp; ${createClientList(clientListHTML)}`, true);
        updateElement(statusCountHA, `<b>${clientListHA.length}</b>&nbsp; ${createClientList(clientListHA)}`, true);
        updateElement(statusCountPC, `<b>${clientListPC.length}</b>&nbsp; ${createClientList(clientListPC)}`, true);

        if (isArmed) {
            if (document.body.classList.contains('is-disarmed') ||
                !document.body.classList.contains('is-armed')) {
                document.body.classList.remove('is-disarmed');
                document.body.classList.add('is-armed');
            }

            if (btnKill.classList.contains('disabled') || btnIgnore.classList.contains('disabled')) {
                btnKill.classList.remove('disabled');
                btnIgnore.classList.remove('disabled');
            }

            updateElement(statusArmed, 'True');
            updateElement(btnArm, '🔌 Disarm ICE');
        } else {
            if (document.body.classList.contains('is-armed') ||
                !document.body.classList.contains('is-disarmed')) {
                document.body.classList.remove('is-armed');
                document.body.classList.add('is-disarmed');
            }

            if (!btnKill.classList.contains('disabled') || !btnIgnore.classList.contains('disabled')) {
                btnKill.classList.add('disabled');
                btnIgnore.classList.add('disabled');
            }

            updateElement(statusArmed, 'False');
            updateElement(btnArm, '🚨 Arm ICE');
        }
    }

    function updateHeartbeat() {
        const timeDiff = Date.now() - heartbeatTimestamp.getTime();
        isConected = timeDiff < 1000 && socket.connected; // 1 second

        if (!isConected) {
            const timeNow = new Date();
            internalEvent = {
                'event': 'disconnected',
                'type': 'connection',
                'source': 'self',
                'timestamp': timeNow.toISOString()
            }
            handleInternalEvent(internalEvent);
            updatePage();
        } else {
            if (flashEventSource === 'connection_disconnected') {
                removeFlash();
            }
        }
    }

    function onDisconnect(event, message) {
        isConected = false;
        updatePage();
        console.log(event)
        console.log(message)

        const timeNow = new Date();
        internalEvent = {
            'event': 'disconnected',
            'type': 'connection',
            'source': 'self',
            'timestamp': timeNow.toISOString()
        }
        handleInternalEvent(internalEvent);
    }

    function generateUUID() {
        let d = new Date().getTime();
        let uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            let r = (d + Math.random() * 16) % 16 | 0;
            d = Math.floor(d / 16);
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
        return uuid;
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
        handleEvent(data['event'], false);
    });

    socket.on('event_ignored', (data) => {
        handleEvent(data['event'], true);
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
                handleEvent(event, false);
            });
        }

        socket.emit('pong');

        // Update heartbeat
        heartbeatTimestamp = new Date();
        updateHeartbeat();

        // Connected client count check
        if (isArmed &&
            (clientListPC.length === 0 ||
            clientListHA.length === 0 ||
            clientListHTML.length === 0)) {

            const timeNow = new Date();
            internalEvent = {
                'event': 'zero_client',
                'type': 'client',
                'source': 'self',
                'timestamp': timeNow.toISOString()
            }
            handleInternalEvent(internalEvent);
        } else {
            if (flashEventSource === 'client_zero_client') {
                removeFlash();
            }
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
        triggerEvent('kill', true);
    });

    btnArm.addEventListener('click', () => {
        socket.emit('set_armed', {'armed': !isArmed});
    });

    btnRecover.addEventListener('click', () => {
        triggerEvent('recover', false);
    });

    btnIgnore.addEventListener('click', () => {
        triggerEvent('ignore', false);
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
        const response = await fetch('/api/v1/go2rtc-config');
        if (!response.ok) {
            // Internal Notify
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsURL = `${wsScheme}://${data.host}/api/ws?src=${data.src}&mode=webrtc`;

        const pc = await PeerConnection(media);
        const ws = new WebSocket(wsURL);

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

        pc.addEventListener('connectionstatechange', () => {
            cameraState = pc.connectionState;
            onCameraStateChanged(cameraState);
            console.log('Connection state changed:', pc.connectionState);
        });

        pc.addEventListener('iceconnectionstatechange', () => {
            console.log('ICE connection state changed:', pc.iceConnectionState);
        });

        pc.addEventListener('signalingstatechange', () => {
            console.log('Signaling state changed:', pc.signalingState);
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
    setInterval(() => {
        if (cameraState !== 'connected' && cameraState !== 'connecting') {
            connect('video+audio');
        }
    }, 1000)
})