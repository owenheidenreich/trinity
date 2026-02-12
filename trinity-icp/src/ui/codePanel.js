// ============================================================================
// CODE PANEL — Persistent side panel for viewing code blocks (Claude-style)
// ============================================================================
// - Persistent right-side panel (35% width) with file dropdown
// - Auto-opens when AI generates code (disabled on mobile)
// - Shows latest response's code blocks only
// - Live streaming of code tokens into the panel
// ============================================================================

import { copyToClipboard, downloadCode, getFileIcon } from '../utils/codeUtils.js';
import State from '../state/store.js';

let containerEl = null;   // #codePanelContainer
let selectEl = null;      // <select> dropdown
let codeEl = null;        // <code> element in body
let preEl = null;         // <pre> wrapping codeEl
let currentBlocks = [];   // Array of {code, language, filename, index}
let selectedIndex = 0;    // Currently displayed block index

/**
 * Initialize the persistent code panel.
 * Call once from app.js after DOM is ready.
 */
export function initCodePanel() {
    containerEl = document.getElementById('codePanelContainer');
    if (!containerEl) {
        console.error('❌ #codePanelContainer not found in DOM');
        return;
    }

    containerEl.innerHTML = `
        <div class="code-panel-header">
            <div class="code-panel-title-row">
                <select class="code-panel-file-select" title="Select file"></select>
            </div>
            <div class="code-panel-actions">
                <button class="code-panel-copy-btn" title="Copy code">Copy</button>
                <button class="code-panel-refresh-btn" title="Refresh">↻</button>
                <button class="code-panel-close-btn" title="Close panel">✕</button>
            </div>
        </div>
        <div class="code-panel-body">
            <div class="code-panel-line-numbers"></div>
            <pre><code></code></pre>
        </div>
    `;

    selectEl = containerEl.querySelector('.code-panel-file-select');
    codeEl = containerEl.querySelector('.code-panel-body code');
    preEl = containerEl.querySelector('.code-panel-body pre');

    // Wire dropdown change
    selectEl.addEventListener('change', () => {
        selectedIndex = parseInt(selectEl.value, 10) || 0;
        renderSelectedBlock();
    });

    // Wire close
    containerEl.querySelector('.code-panel-close-btn').addEventListener('click', closeCodePanel);

    // Wire copy
    const copyBtn = containerEl.querySelector('.code-panel-copy-btn');
    copyBtn.addEventListener('click', () => {
        const block = currentBlocks[selectedIndex];
        if (block) copyToClipboard(block.code, copyBtn);
    });

    // Wire refresh (re-render / re-highlight)
    containerEl.querySelector('.code-panel-refresh-btn').addEventListener('click', () => {
        renderSelectedBlock();
    });

    // Keyboard shortcut
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && State.codePanelOpen) {
            closeCodePanel();
        }
    });

    console.log('✅ Code panel initialized');
}

/**
 * Set the code blocks to display and open the panel.
 * @param {Array<{code: string, language: string, filename: string}>} blocks
 * @param {Object} [options]
 * @param {boolean} [options.autoOpen=true] - Whether to auto-open the panel
 */
export function setCodeBlocks(blocks, { autoOpen = true } = {}) {
    currentBlocks = blocks || [];
    State.setCodePanelBlocks(currentBlocks);

    // Populate dropdown
    if (selectEl) {
        selectEl.innerHTML = '';
        currentBlocks.forEach((block, i) => {
            const opt = document.createElement('option');
            opt.value = i;
            const ext = (block.filename || '').split('.').pop() || '';
            const name = block.displayName || block.filename;
            opt.textContent = `${name} · ${ext.toUpperCase()}`;
            selectEl.appendChild(opt);
        });
    }

    // Select first block
    selectedIndex = 0;
    if (selectEl) selectEl.value = '0';
    renderSelectedBlock();

    // Auto-open (unless mobile)
    if (autoOpen && currentBlocks.length > 0 && !isMobile()) {
        openCodePanel();
    }
}

/**
 * Select a specific block by index and open the panel.
 */
export function selectBlock(index) {
    if (index >= 0 && index < currentBlocks.length) {
        selectedIndex = index;
        if (selectEl) selectEl.value = String(index);
        renderSelectedBlock();
        openCodePanel();
    }
}

/**
 * Update streaming content for in-progress code block.
 * Called during token streaming for the block being actively written.
 * @param {string} partialCode - The partial code so far
 * @param {string} language - The language
 */
export function updateStreamingBlock(partialCode, language) {
    if (!codeEl || !containerEl) return;

    // Show streaming content directly
    codeEl.textContent = partialCode;
    codeEl.className = language ? `language-${language}` : '';

    // Don't highlight during streaming (too expensive per-token)
    // Highlighting happens on final render via renderSelectedBlock()
}

/**
 * Open the code panel.
 */
export function openCodePanel() {
    if (!containerEl) return;
    const appContainer = document.querySelector('.app-container');
    if (appContainer) appContainer.classList.add('panel-open');
    containerEl.classList.add('open');
    State.setCodePanelOpen(true);
}

/**
 * Close the code panel.
 */
export function closeCodePanel() {
    if (!containerEl) return;
    const appContainer = document.querySelector('.app-container');
    if (appContainer) appContainer.classList.remove('panel-open');
    containerEl.classList.remove('open');
    State.setCodePanelOpen(false);
}

/**
 * Get current code blocks array.
 */
export function getCodeBlocks() {
    return currentBlocks;
}

/**
 * Check if the device is mobile.
 */
function isMobile() {
    return window.innerWidth <= 768;
}

/**
 * Render the currently selected block into the panel body.
 */
function renderSelectedBlock() {
    if (!codeEl) return;

    const block = currentBlocks[selectedIndex];
    const lineNumbersEl = containerEl?.querySelector('.code-panel-line-numbers');

    if (!block) {
        codeEl.textContent = '';
        codeEl.className = '';
        if (lineNumbersEl) lineNumbersEl.innerHTML = '';
        return;
    }

    codeEl.textContent = block.code;
    codeEl.className = block.language ? `language-${block.language}` : '';

    // Syntax highlight
    if (typeof hljs !== 'undefined') {
        codeEl.classList.remove('hljs');
        hljs.highlightElement(codeEl);
    }

    // Generate line numbers
    if (lineNumbersEl) {
        const lineCount = (block.code || '').split('\n').length;
        lineNumbersEl.innerHTML = Array.from({ length: lineCount }, (_, i) =>
            `<span>${i + 1}</span>`
        ).join('\n');
    }
}

export default { initCodePanel, openCodePanel, closeCodePanel, setCodeBlocks, selectBlock, updateStreamingBlock, getCodeBlocks };
