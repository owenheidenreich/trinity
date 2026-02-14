// ============================================================================
// TRINITY INTEGRATED TOOLS - File Attachments
// ============================================================================

import CONFIG from './config.js';
import Logger from './core/logger.js';

// File size limits
const MAX_TEXT_SIZE_KB = 100;
const MAX_TEXT_SIZE_BYTES = MAX_TEXT_SIZE_KB * 1024;

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
    
    if (file.size > MAX_TEXT_SIZE_BYTES) {
        alert(`File too large. Maximum size is ${MAX_TEXT_SIZE_KB}KB.`);
        event.target.value = '';
        return;
    }
    await handleTextFile(file);
}

async function handleTextFile(file) {
    try {
        const content = await file.text();
        attachedFile = file;
        attachedContent = content;
        showAttachmentPreview(file.name, file.size);
        Logger.debug(`File attached: ${file.name}`);
    } catch (error) {
        Logger.error('Error reading file:', error);
        alert('Error reading file: ' + error.message);
    }
}

function showAttachmentPreview(filename, size) {
    const preview = document.getElementById('attachedFilePreview');
    const nameEl = document.getElementById('attachedFileName');
    const sizeEl = document.getElementById('attachedFileSize');
    
    if (!preview || !nameEl || !sizeEl) return;
    
    nameEl.textContent = `📄 ${filename}`;
    sizeEl.textContent = formatFileSize(size);
    
    preview.style.display = 'flex';
}

// ============================================================================
// INITIALIZATION
// ============================================================================

function initTools() {
    Logger.debug('Initializing integrated tools...');
    
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
    
    Logger.debug('Integrated tools ready');
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
