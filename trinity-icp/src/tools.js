// ============================================================================
// TRINITY INTEGRATED TOOLS - File Attachments, Audio Transcription
// ============================================================================

import CONFIG from './config.js';

// File size limits
const MAX_TEXT_SIZE_KB = 100;
const MAX_AUDIO_SIZE_MB = 25;
const MAX_TEXT_SIZE_BYTES = MAX_TEXT_SIZE_KB * 1024;
const MAX_AUDIO_SIZE_BYTES = MAX_AUDIO_SIZE_MB * 1024 * 1024;

// Current state
let attachedFile = null;
let attachedContent = null;

// ============================================================================
// FILE ATTACHMENT
// ============================================================================

function getAttachedContent() {
    return attachedContent;
}

function clearAttachment() {
    attachedFile = null;
    attachedContent = null;
    
    const preview = document.getElementById('attachedFilePreview');
    if (preview) preview.style.display = 'none';
    
    const fileInput = document.getElementById('fileInput');
    if (fileInput) fileInput.value = '';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const isAudio = file.type.startsWith('audio/') || 
                    /\.(mp3|wav|m4a|ogg|webm|flac)$/i.test(file.name);
    
    if (isAudio) {
        if (file.size > MAX_AUDIO_SIZE_BYTES) {
            alert(`Audio file too large. Maximum size is ${MAX_AUDIO_SIZE_MB}MB.`);
            event.target.value = '';
            return;
        }
        await handleAudioFile(file);
    } else {
        if (file.size > MAX_TEXT_SIZE_BYTES) {
            alert(`Text file too large. Maximum size is ${MAX_TEXT_SIZE_KB}KB.`);
            event.target.value = '';
            return;
        }
        await handleTextFile(file);
    }
}

async function handleTextFile(file) {
    try {
        const content = await file.text();
        attachedFile = file;
        attachedContent = content;
        showAttachmentPreview(file.name, file.size, 'text');
        console.log(`Text file attached: ${file.name}`);
    } catch (error) {
        console.error('Error reading file:', error);
        alert('Error reading file: ' + error.message);
    }
}

async function handleAudioFile(file) {
    try {
        showAttachmentPreview(file.name, file.size, 'audio', true);
        
        const formData = new FormData();
        formData.append('audio', file);
        
        console.log(`Transcribing audio: ${file.name}...`);
        
        const response = await fetch(`${CONFIG.API_URL}/tools/audio/transcribe`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        attachedFile = file;
        attachedContent = result.transcript;
        
        showAttachmentPreview(file.name, file.size, 'audio', false, 
            `Transcribed: ${result.transcript.length} chars`);
        
        console.log(`Audio transcribed: ${result.transcript.length} chars`);
        
    } catch (error) {
        console.error('Transcription error:', error);
        clearAttachment();
        alert('Transcription failed: ' + error.message);
    }
}

function showAttachmentPreview(filename, size, type, loading = false, extra = '') {
    const preview = document.getElementById('attachedFilePreview');
    const nameEl = document.getElementById('attachedFileName');
    const sizeEl = document.getElementById('attachedFileSize');
    
    if (!preview || !nameEl || !sizeEl) return;
    
    const icon = type === 'audio' ? '🎤' : '📄';
    nameEl.textContent = `${icon} ${filename}`;
    
    if (loading) {
        sizeEl.innerHTML = '<span class="transcribing-indicator">Transcribing...</span>';
    } else {
        sizeEl.textContent = extra || formatFileSize(size);
    }
    
    preview.style.display = 'flex';
}

// ============================================================================
// INITIALIZATION
// ============================================================================

function initTools() {
    console.log('Initializing integrated tools...');
    
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');
    
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelect);
    }
    
    const removeBtn = document.getElementById('removeAttachment');
    if (removeBtn) {
        removeBtn.addEventListener('click', clearAttachment);
    }
    
    console.log('Integrated tools ready');
}

export { 
    initTools, 
    getAttachedContent, 
    clearAttachment
};
export default { 
    initTools, 
    getAttachedContent, 
    clearAttachment
};
