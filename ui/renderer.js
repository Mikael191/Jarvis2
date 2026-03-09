const orb = document.getElementById('jarvis-orb'); // legacy fallback
const statusText = document.getElementById('status-text');
const transcriptText = document.getElementById('transcript-text');

const STATE_LABELS = {
    idle: 'SISTEMA ATIVO',
    listening: 'OUVINDO...',
    thinking: 'PROCESSANDO...',
    speaking: 'RESPONDENDO...',
};

function setBodyState(state) {
    document.body.className = state;            // body class drives all CSS states
    statusText.innerText = STATE_LABELS[state] || state.toUpperCase();
}

function setTranscript(sender, text) {
    transcriptText.innerText = text;
    transcriptText.style.color =
        sender === 'user' ? 'rgba(255,255,255,.7)' :
            sender === 'jarvis' ? '#00dcff' : '#666';
}

window.electronAPI.onJarvisEvent((event) => {
    if (event.type === 'state') {
        setBodyState(event.status);
    }
    if (event.type === 'log') {
        setTranscript(event.sender, event.text);
    }
});

// Default state on load
document.addEventListener('DOMContentLoaded', () => setBodyState('idle'));
