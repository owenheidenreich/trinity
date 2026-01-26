// ============================================================================
// AI TOOLS MODULE - Chat with Docs, Transcript Cleaner, PicklesGPT
// ============================================================================

import CONFIG from './config.js';

let documentSessionId = null;
let picklesContext = [];

const ToolsAPI = {
    async uploadDocument(content, filename) {
        const response = await fetch(`${CONFIG.API_URL}/tools/documents/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, filename, sessionId: Date.now().toString() })
        });
        return response.json();
    },
    async queryDocument(sessionId, query) {
        const response = await fetch(`${CONFIG.API_URL}/tools/documents/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId, query })
        });
        return response.json();
    },
    async cleanTranscript(text) {
        const response = await fetch(`${CONFIG.API_URL}/tools/transcript/clean`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        return response.json();
    },
    async chatWithPickles(message, contextMemory) {
        const response = await fetch(`${CONFIG.API_URL}/tools/pickles/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, contextMemory })
        });
        return response.json();
    }
};

function switchTool(toolName) {
    document.querySelectorAll('.tool-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tool === toolName);
    });
    document.querySelectorAll('.tool-view').forEach(view => {
        view.style.display = 'none';
        view.classList.remove('active');
    });
    const view = document.getElementById(toolName + 'View');
    if (view) {
        view.style.display = 'flex';
        view.classList.add('active');
    }
    console.log(`🔧 Switched to: ${toolName}`);
}

async function handleDocumentUpload() {
    const content = document.getElementById('docContent').value;
    const statusEl = document.getElementById('docStatus');
    const querySection = document.getElementById('docQuerySection');
    if (!content.trim()) {
        statusEl.textContent = 'Please enter document content';
        statusEl.className = 'status-msg error';
        return;
    }
    statusEl.textContent = 'Loading...';
    statusEl.className = 'status-msg';
    try {
        const result = await ToolsAPI.uploadDocument(content, 'document.txt');
        if (result.error) throw new Error(result.error);
        documentSessionId = result.sessionId;
        statusEl.textContent = `Loaded (${result.documentLength} chars)`;
        statusEl.className = 'status-msg success';
        querySection.style.display = 'block';
    } catch (err) {
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.className = 'status-msg error';
    }
}

async function handleDocumentQuery() {
    const query = document.getElementById('docQuery').value;
    const answerEl = document.getElementById('docAnswer');
    const btn = document.getElementById('queryDocBtn');
    if (!query.trim() || !documentSessionId) return;
    btn.disabled = true;
    answerEl.textContent = 'Thinking...';
    try {
        const result = await ToolsAPI.queryDocument(documentSessionId, query);
        if (result.error) throw new Error(result.error);
        answerEl.textContent = result.answer;
    } catch (err) {
        answerEl.textContent = 'Error: ' + err.message;
    } finally {
        btn.disabled = false;
    }
}

async function handleTranscriptClean() {
    const raw = document.getElementById('rawTranscript').value;
    const statusEl = document.getElementById('transcriptStatus');
    const cleanedSection = document.getElementById('cleanedSection');
    const cleanedEl = document.getElementById('cleanedTranscript');
    const btn = document.getElementById('cleanTranscriptBtn');
    if (!raw.trim()) {
        statusEl.textContent = 'Please enter a transcript';
        statusEl.className = 'status-msg error';
        return;
    }
    btn.disabled = true;
    statusEl.textContent = 'Cleaning...';
    statusEl.className = 'status-msg';
    try {
        const result = await ToolsAPI.cleanTranscript(raw);
        if (result.error) throw new Error(result.error);
        cleanedEl.value = result.cleanedText;
        cleanedSection.style.display = 'block';
        statusEl.textContent = `Done (${result.originalLength} → ${result.cleanedLength} chars)`;
        statusEl.className = 'status-msg success';
    } catch (err) {
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.className = 'status-msg error';
    } finally {
        btn.disabled = false;
    }
}

async function handlePicklesChat() {
    const input = document.getElementById('picklesInput');
    const messagesEl = document.getElementById('picklesMessages');
    const btn = document.getElementById('sendPicklesBtn');
    const message = input.value.trim();
    if (!message) return;

    const userMsg = document.createElement('div');
    userMsg.className = 'pickles-msg user';
    userMsg.innerHTML = `<strong>You:</strong> ${escapeHtml(message)}`;
    messagesEl.appendChild(userMsg);
    picklesContext.push({ role: 'user', content: message });
    input.value = '';
    btn.disabled = true;

    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'pickles-msg assistant';
    thinkingEl.innerHTML = '<strong>Pickles:</strong> <em>Thinking...</em>';
    messagesEl.appendChild(thinkingEl);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    try {
        const result = await ToolsAPI.chatWithPickles(message, picklesContext);
        if (result.error) throw new Error(result.error);
        thinkingEl.innerHTML = `<strong>Pickles:</strong> ${escapeHtml(result.response)}`;
        picklesContext.push({ role: 'assistant', content: result.response });
        if (picklesContext.length > 10) picklesContext = picklesContext.slice(-10);
    } catch (err) {
        thinkingEl.innerHTML = `<strong>Pickles:</strong> <em style="color:#f44336;">Error: ${escapeHtml(err.message)}</em>`;
    } finally {
        btn.disabled = false;
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => { document.getElementById('docContent').value = e.target.result; };
    reader.readAsText(file);
}

function initTools() {
    console.log('🔧 Initializing AI Tools...');
    document.querySelectorAll('.tool-nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTool(btn.dataset.tool));
    });
    document.getElementById('uploadDocBtn')?.addEventListener('click', handleDocumentUpload);
    document.getElementById('docFileInput')?.addEventListener('change', handleFileUpload);
    document.getElementById('queryDocBtn')?.addEventListener('click', handleDocumentQuery);
    document.getElementById('docQuery')?.addEventListener('keydown', e => { if (e.key === 'Enter') handleDocumentQuery(); });
    document.getElementById('cleanTranscriptBtn')?.addEventListener('click', handleTranscriptClean);
    document.getElementById('sendPicklesBtn')?.addEventListener('click', handlePicklesChat);
    document.getElementById('picklesInput')?.addEventListener('keydown', e => { if (e.key === 'Enter') handlePicklesChat(); });
    console.log('✅ AI Tools ready');
}

export { initTools, switchTool, ToolsAPI };
export default { initTools, switchTool, ToolsAPI };
