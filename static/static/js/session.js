const paramsString = window.location.search;
const searchParams = new URLSearchParams(paramsString);

const clientName = searchParams.get('clientName');
const warnDuration = 10 * 1000; // 10 seconds

const warnAudio = new Audio('/static/media/warn.wav');
let soundTimeoutId;

if (!clientName) {
    alert('Client name not set. Redirecting to home...');
    window.location.href = '/';
}

document.addEventListener('DOMContentLoaded', () => {

    // Elements
    const btnKill = document.getElementById('btnKill');
    const btnIgnore = document.getElementById('btnIgnore');
    const btnArm = document.getElementById('btnArm');
    const btnArmStandalone = document.getElementById('btnArmStandalone');
    const btnRecover = document.getElementById('btnRecover');
    const btnToggleFullscreen = document.getElementById('btnToggleFullscreen');
    const btnClearLog = document.getElementById('btnClearLog');

    const logContainer = document.getElementById('logContainer');
    const checkboxWarnSound = document.getElementById('checkboxWarnSound');

    const modal = document.getElementById('modal');
    const modalTitle = document.getElementById('modalTitle');
    const modalMessage = document.getElementById('modalMessage');
    const modalBtnWrapper = document.getElementById('modalBtnWrapper');

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

    let isArmed = false;
    let isArmedStandalone = false;
    let isConected = false;
    let heartbeatTimestamp = new Date(0);
    let cameraState = null;

    let lastEventID = null;
    let emitedEventList = [];
    let receivedEventList = [];
    let flashEventSource = null;
    let videoOverlayEventSource = null;

    let clientListPC = [];
    let clientListHA = [];
    let clientListHTML = [];

    let oldClientListPC = [];
    let oldClientListHA = [];
    let oldClientListHTML = [];

    let lastOnvifTimestamp = new Date(0);

    const socket = io({
        transports: ['websocket', 'polling'],
        upgrade: true,
        rememberUpgrade: false,
        timeout: 1000,
        forceNew: true
    });

    function _showModal(title, message, buttons) {
        // Remove existing buttons
        modalBtnWrapper.innerHTML = '';

        // Set modal content
        modalTitle.innerText = title;
        modalMessage.innerText = message;

        // Create and append buttons
        buttons.forEach(btnConfig => {
            const btn = document.createElement('button');
            btn.innerText = btnConfig.text;
            btn.classList.add('modal-button');

            if (btnConfig.type) {
                btn.classList.add(btnConfig.type);
            }

            btn.addEventListener('click', () => {
                if (btnConfig.callback) {
                    btnConfig.callback();
                }
                hideModal();
            });
            modalBtnWrapper.appendChild(btn);
        });

        // Display the modal
        modal.classList.add('is-visible');
    }

    function modalConfirm(title, message, options = {}) {
        const buttons = [
            {
                text: 'Confirm',
                type: 'action',
                callback: options.confirmCallback,
            },
            {
                text: 'Cancel',
                type: '',
                callback: options.cancelCallback,
            }
        ];
        _showModal(title, message, buttons);
    }

    function modalAlert(title, message, options = {}) {
        const buttons = [
            {
                text: 'OK',
                type: '',
                callback: options.okCallback,
            }
        ];
        _showModal(title, message, buttons);
    }

    function hideModal() {
        modal.classList.remove('is-visible');
    }

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

            if (timeDiff < warnDuration && event['type'] === eventType) {
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
        socket.emit('ack', {
            'id': eventObj['id'],
        });

        lastEventID = eventObj['id'];

        if (isIgnored && !isArmedStandalone) {
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

        } else if (isArmedStandalone) {
            if (eventObj['type'] === 'onvif' && !isPreviousEventValid('onvif')) {
                addLogEntry(`ONVIF: ${capitalizeFirstLetter(eventObj['event'])} Detected!`, true);

                const timeNow = new Date();
                const timeDiff = timeNow.getTime() - lastOnvifTimestamp.getTime();

                if (timeDiff > warnDuration) {
                    lastOnvifTimestamp = new Date();

                    flash(`${eventObj['type']}_${eventObj['event']}`);
                    showVideoOverlay(`${eventObj['type']}_${eventObj['event']}`, `${eventObj['event'].toUpperCase()} DETECTED!`);

                    if (checkboxWarnSound.checked) {
                        startSound();
                    }
                }

            } else if (eventObj['type'] === 'user' && !isEmitedEvent(eventObj['id'])) {
                if (eventObj['event'] === 'kill') {
                    addLogEntry(`USER: User broadcasted event '${eventObj['event'].toUpperCase()}' with mode '${eventObj['data']['killMode'].toUpperCase()}'.`, true);
                } else {
                    addLogEntry(`USER: User broadcasted event '${eventObj['event'].toUpperCase()}'.`, true);
                }

            } else if (eventObj['type'] === 'client') {
                addLogEntry(`CLIENT: Client '${eventObj['data']['client']['name']}' ${eventObj['event']}.`);
            }

        } else {
            if (eventObj['type'] === 'onvif' && !isPreviousEventValid('onvif')) {
                receivedEventList.push(eventObj);
                addLogEntry(`ONVIF: ${capitalizeFirstLetter(eventObj['event'])} Detected!`, true);

                const timeNow = new Date();
                const timeDiff = timeNow.getTime() - lastOnvifTimestamp.getTime();

                if (timeDiff > warnDuration) {
                    lastOnvifTimestamp = new Date();

                    flash(`${eventObj['type']}_${eventObj['event']}`);
                    showVideoOverlay(`${eventObj['type']}_${eventObj['event']}`, `${eventObj['event'].toUpperCase()} DETECTED!`);

                    if (checkboxWarnSound.checked) {
                        startSound();
                    }
                }

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
                    showVideoOverlay(`${eventObj['type']}_${eventObj['event']}`, `CLIENT '${eventObj['data']['client']['name']}' DISCONNECTED!`);
                }
            } else if (eventObj['type'] === 'user' && eventObj['event'] === 'ignore') {
                receivedEventList.push(eventObj);
                if (flashEventSource !== null) {
                    removeFlash();
                }
                if (videoOverlayEventSource !== null) {
                    removeVideoOverlay();
                }
                stopSound();
            }
        }
    }

    function handleInternalEvent(eventObj) {
        if (!isPreviousEventValid(eventObj['type'], eventObj['event'])) {
            receivedEventList.push(eventObj);
            if (eventObj['event'] === 'zero_client') {
                addLogEntry(`CLIENT: Zero client detected: PC: ${clientListPC.length}, HA: ${clientListHA.length}, HTML: ${clientListHTML.length}`, true);
                showVideoOverlay(`${eventObj['type']}_${eventObj['event']}`, `ZERO CLIENT DETECTED!`);
            } else if (eventObj['event'] === 'disconnected') {
                addLogEntry(`CONNECTION: Connection to server lost.`, true);
                showVideoOverlay(`${eventObj['type']}_${eventObj['event']}`, `CONNECTION LOST!`);
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

        setTimeout(removeFlash, warnDuration);
    }

    function removeFlash(eventName = null) {
        if (eventName !== null && eventName !== flashEventSource) {
            console.log('Tried to dismiss non-matching event\'s flash.');
            return;
        }
        document.body.classList.remove('flash-red');
        videoOverlayElem.classList.remove('flash-red');
        flashEventSource = null;
    }

    function triggerEvent(eventName, isKill) {
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

    function showVideoOverlay(eventName, message) {

        videoOverlayMessage.innerText = message;
        videoOverlayElem.style.display = 'block';
        videoOverlayEventSource = eventName;

        setTimeout(removeVideoOverlay, warnDuration);
    }

    function removeVideoOverlay(eventName = null) {
        if (eventName !== null && eventName !== videoOverlayEventSource) {
            console.log('Tried to dismiss non-matching event\'s video overlay.');
            return;
        }
        videoOverlayMessage.innerText = '';
        videoOverlayElem.style.display = 'none';
        videoOverlayEventSource = null;
    }

    function addLogEntry(message, isPriority = false) {
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

    function armStandalone(setArmedStandalone) {
        isArmedStandalone = setArmedStandalone;

        updatePage();
    }

    function updateElement(element, newContent, isHTML = false) {
        if (!isHTML && element.innerText != newContent) {
            element.innerText = newContent;
        } else if (isHTML && element.innerHTML != newContent) {
            element.innerHTML = newContent;
        }
    }

    function updatePage() {
        if (!isArmed) {
            if (flashEventSource !== null) {
                removeFlash();
            }
            if (videoOverlayEventSource !== null) {
                removeVideoOverlay();
            }
        }

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
        if (clientListPC !== oldClientListPC || clientListHA !== oldClientListHA || clientListHTML !== oldClientListHTML) {
            updateElement(statusCountHTML, `<b>${clientListHTML.length}</b>&nbsp; ${createClientList(clientListHTML)}`, true);
            updateElement(statusCountHA, `<b>${clientListHA.length}</b>&nbsp; ${createClientList(clientListHA)}`, true);
            updateElement(statusCountPC, `<b>${clientListPC.length}</b>&nbsp; ${createClientList(clientListPC)}`, true);
            oldClientListPC = clientListPC;
            oldClientListHA = clientListHA;
            oldClientListHTML = clientListHTML;
        }

        if (isArmed && isArmedStandalone) {
            armStandalone(false);

        } else if (isArmed) {
            if (document.body.classList.contains('is-disarmed') ||
                document.body.classList.contains('is-standalone') ||
                !document.body.classList.contains('is-armed')) {
                document.body.classList.remove('is-disarmed');
                document.body.classList.remove('is-standalone');
                document.body.classList.add('is-armed');
            }

            if (btnKill.classList.contains('disabled') || btnIgnore.classList.contains('disabled')) {
                btnKill.classList.remove('disabled');
                btnIgnore.classList.remove('disabled');
            }

            if (btnArm.style.display !== 'block') {
                btnArm.style.display = 'block'
            }

            if (btnArmStandalone.style.display !== 'none') {
                btnArmStandalone.style.display = 'none'
            }

            updateElement(statusArmed, 'True');
            updateElement(btnArm, '🔌 Disarm ICE');

        } else if (isArmedStandalone) {
            if (document.body.classList.contains('is-disarmed') ||
                document.body.classList.contains('is-armed') ||
                !document.body.classList.contains('is-standalone')) {
                document.body.classList.remove('is-disarmed');
                document.body.classList.remove('is-armed');
                document.body.classList.add('is-standalone');
            }

            if (btnKill.classList.contains('disabled') || btnIgnore.classList.contains('disabled')) {
                btnKill.classList.remove('disabled');
                btnIgnore.classList.remove('disabled');
            }

            if (btnArm.style.display !== 'none') {
                btnArm.style.display = 'none'
            }

            if (btnArmStandalone.style.display !== 'block') {
                btnArmStandalone.style.display = 'block'
            }

            updateElement(statusArmed, 'Standalone');
            updateElement(btnArmStandalone, '🔌 Disarm Standalone');

        } else {
            if (document.body.classList.contains('is-armed') ||
                document.body.classList.contains('is-standalone') ||
                !document.body.classList.contains('is-disarmed')) {
                document.body.classList.remove('is-armed');
                document.body.classList.remove('is-standalone');
                document.body.classList.add('is-disarmed');
            }

            if (!btnKill.classList.contains('disabled') || !btnIgnore.classList.contains('disabled')) {
                btnKill.classList.add('disabled');
                btnIgnore.classList.add('disabled');
            }

            if (btnArm.style.display !== 'block') {
                btnArm.style.display = 'block'
            }

            if (btnArmStandalone.style.display !== 'block') {
                btnArmStandalone.style.display = 'block'
            }

            updateElement(statusArmed, 'False');
            updateElement(btnArm, '🚨 Arm ICE');
            updateElement(btnArmStandalone, '🚨 Arm Standalone');
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
                removeFlash('connection_disconnected');
            }
            if (videoOverlayEventSource === 'connection_disconnected') {
                removeVideoOverlay('connection_disconnected');
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

    async function requestWakeLock() {
        try {
            wakeLock = await navigator.wakeLock.request('screen');
        } catch (err) {
            console.error(`Error requesting Wake Lock: ${err.name}, ${err.message}`);
        }
    }

    function releaseWakeLock() {
        if (wakeLock !== null) {
            wakeLock.release();
            wakeLock = null;
        }
    }

    function startSound() {
        if (soundTimeoutId) {
            return; // Prevent duplicate sound
        }

        // Function to play the sound and set up the next one
        function playNextSound() {
            warnAudio.play();
        }

        playNextSound(); // Start the first playback

        // When the sound ends, re-start the loop
        warnAudio.onended = () => {
            // This will be called whenever the sound finishes playing
            playNextSound();
        };

        // Set a timeout to automatically stop the sound after warnDuration
        soundTimeoutId = setTimeout(() => {
            stopSound();
        }, warnDuration);
    }

    function stopSound() {
        // Pause the audio and reset it to the beginning
        warnAudio.pause();
        warnAudio.currentTime = 0;

        // Remove the onended event listener to stop the loop
        warnAudio.onended = null;

        // Check if a timeout ID exists
        if (soundTimeoutId) {
            clearTimeout(soundTimeoutId); // Clear the timeout
            soundTimeoutId = null; // Clear the variable
        }
    }

    socket.on('connect', () => {
        heartbeatTimestamp = new Date();
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
        handleEvent(data['event'], !isArmedStandalone);
    });

    socket.on('ping', (data) => {
        socket.emit('get');
    });

    socket.on('get_result', (data) => {
        isArmed = Boolean(data['isArmed']);

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

        let newEventList = [];
        let ackedEventList = [];

        socket.emit('pong');

        function isDuplicateEvent(eventID) {
            for (const event of receivedEventList) {
                if (event['id'] === eventID) {
                    return true;
                }
            }
            return false;
        }

        eventList.forEach(event => {
            if (isDuplicateEvent(event['id'])) {
                ackedEventList.push(event['id']);
            } else {
                newEventList.push(event);
            }
        });

        if (newEventList.length > 0) {
            addLogEntry(`Detected a delay in processing event: ${newEventList.length} events in queue`, false)
            newEventList.forEach(event => {
                handleEvent(event, false);
            });
        }

        ackedEventList.forEach(eventID => {
            socket.emit('ack', { // ACK one more time just to make sure
                'id': eventID,
            });
        });

        // Update heartbeat
        heartbeatTimestamp = new Date();
        updateHeartbeat();

        // Connected client count check
        if (isArmed && (clientListPC.length === 0 || clientListHA.length === 0 || clientListHTML.length === 0)) {
            const timeNow = new Date();
            internalEvent = {
                'event': 'zero_client',
                'type': 'client',
                'source': 'self',
                'timestamp': timeNow.toISOString()
            }
            handleInternalEvent(internalEvent);
        } else if (isArmed) {
            if (flashEventSource === 'client_zero_client') {
                removeFlash('client_zero_client');
            }
            if (videoOverlayEventSource === 'client_zero_client') {
                removeVideoOverlay('client_zero_client');
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
        if (!isArmed) {
            modalAlert('ERROR', 'ICE isn\'t armed.');
            return;
        }
        triggerEvent('kill', true);
    });

    btnArm.addEventListener('click', () => {
        if (isArmed) {
            modalConfirm(
                'Disarm ICE',
                'Do you want to disarm ICE?',
                {
                    confirmCallback: () => socket.emit('set_armed', {'armed': false})
                }
            );
        } else {
            modalConfirm(
                'Arm ICE',
                'Do you want to arm ICE?',
                {
                    confirmCallback: () => socket.emit('set_armed', {'armed': true})
                }
            );
        }
    });

    btnArmStandalone.addEventListener('click', () => {
        if (isArmedStandalone) {
            modalConfirm(
                'Disarm ICE Standalone',
                'Do you want to disarm ICE Standalone mode?',
                {
                    confirmCallback: () => armStandalone(false)
                }
            );
        } else {
            modalConfirm(
                'Arm ICE Standalone',
                'Do you want to arm ICE Standalone mode?',
                {
                    confirmCallback: () => armStandalone(true)
                }
            );
        }
    });

    btnRecover.addEventListener('click', () => {
        if (!isArmed) {
            modalAlert('ERROR', 'ICE isn\'t armed.')
        } else {
            modalConfirm(
                'Recover State',
                'Do you want to recover the state?',
                {
                    confirmCallback: () => triggerEvent('recover', false)
                }
            );
        }
    });

    btnIgnore.addEventListener('click', () => {
        if (isArmed) {
            triggerEvent('ignore', false);
        } else if (isArmedStandalone) {
            if (flashEventSource !== null) {
                removeFlash();
            }
            if (videoOverlayEventSource !== null) {
                removeVideoOverlay();
            }
            stopSound();
        } else {
            modalAlert('ERROR', 'ICE isn\'t armed.');
        }
    });

    modal.addEventListener('click', (event) => {
        if (event.target === modal) {
            hideModal();
        }
    });

    btnToggleFullscreen.addEventListener('click', () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
            requestWakeLock();
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
                releaseWakeLock();
            }
        }
    });

    btnClearLog.addEventListener('click', () => {
        logContainer.innerHTML = '';
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

    setTimeout(() => { // Wait 1 second for page to initialize
        setInterval(() => {
            updateHeartbeat();

            function clearOldEvents(eventList) {
                const timeNow = new Date();
                return eventList.filter(event => {
                    const timeEvent = new Date(event['timestamp']);
                    const timeDiff = timeNow.getTime() - timeEvent.getTime();
                    return timeDiff < warnDuration;
                });
            }
            emitedEventList = clearOldEvents(emitedEventList);
            receivedEventList = clearOldEvents(receivedEventList);

            updatePage();

            if (!socket.connected) {
                console.log('connecting');
                socket.connect();
            }
        }, 1000);
    }, 1000);

    connect('video+audio');
    setInterval(() => {
        if (cameraState !== 'connected' && cameraState !== 'connecting') {
            connect('video+audio');
        }
    }, 1000)
})