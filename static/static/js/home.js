document.addEventListener('DOMContentLoaded', () => {
    const inputClientName = document.getElementById('inputClientName');
    const btnStart = document.getElementById('btnStart');

    inputClientName.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            btnStart.click();
        }
    });

    btnStart.addEventListener('click', () => {
        const clientName = inputClientName.value;
        if (clientName === '') {
            alert('Client name cannot be empty.');
        } else {
            window.location.href = `/session?clientName=${clientName}`;
        }
    });
});