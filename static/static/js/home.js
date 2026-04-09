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
        if (clientName.trim() === '') {
            alert('Client name cannot be empty.');
        } else {
            const params = new URLSearchParams();
            params.append('clientName', clientName.trim());
            window.location.href = `/session/?${params.toString()}`;
        }
    });
});