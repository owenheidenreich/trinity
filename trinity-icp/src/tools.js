// ============================================================================
// TRINITY INTEGRATED TOOLS - Persona, File Attachments, Audio Transcription
// ============================================================================

import CONFIG from './config.js';
import State from './state/store.js';

// File size limits
const MAX_TEXT_SIZE_KB = 100;
const MAX_AUDIO_SIZE_MB = 25;
const MAX_TEXT_SIZE_BYTES = MAX_TEXT_SIZE_KB * 1024;
const MAX_AUDIO_SIZE_BYTES = MAX_AUDIO_SIZE_MB * 1024 * 1024;

// Current state - load from localStorage for persistence
let currentPersona = localStorage.getItem('trinity_persona') || 'trinity';
let attachedFile = null;
let attachedContent = null;

// ============================================================================
// PERSONA MANAGEMENT
// ============================================================================

function getPersona() {
    return currentPersona;
}

function setPersona(persona) {
    currentPersona = persona;
    
    // Persist to localStorage
    localStorage.setItem('trinity_persona', persona);
    
    // Update UI
    const label = document.getElementById('personaLabel');
    const title = document.getElementById('personaTitle');
    const mainContent = document.querySelector('.main-content');
    
    if (label) label.textContent = persona === 'pickles' ? 'Pickles' : 'Trinity';
    if (title) title.textContent = persona === 'pickles' ? 'PicklesGPT' : 'Trinity';
    
    // Update main content class for persona-specific styling
    if (mainContent) {
        mainContent.classList.toggle('persona-pickles', persona === 'pickles');
    }
    
    // Update active state in dropdown
    document.querySelectorAll('.persona-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.persona === persona);
    });
    
    console.log(`Persona switched to: ${persona} (persisted)`);
}

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
    
    const personaBtn = document.getElementById('personaBtn');
    const personaDropdown = document.getElementById('personaDropdown');
    
    if (personaBtn && personaDropdown) {
        personaBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            personaDropdown.classList.toggle('open');
        });
        
        document.addEventListener('click', (e) => {
            if (!personaDropdown.contains(e.target)) {
                personaDropdown.classList.remove('open');
            }
        });
        
        document.querySelectorAll('.persona-option').forEach(opt => {
            opt.addEventListener('click', () => {
                setPersona(opt.dataset.persona);
                personaDropdown.classList.remove('open');
            });
        });
        
        // Restore persisted persona on page load
        const savedPersona = localStorage.getItem('trinity_persona');
        if (savedPersona && (savedPersona === 'trinity' || savedPersona === 'pickles')) {
            setPersona(savedPersona);
            console.log(`Restored persona from localStorage: ${savedPersona}`);
        }
    }
    
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

export { initTools, getPersona, setPersona, getAttachedContent, clearAttachment };
export default { initTools, getPersona, setPersona, getAttachedContent, clearAttachment };
