// ============================================================================
// EDIT MESSAGE UI — User message editing with regeneration
// ============================================================================
// Allows users to edit sent messages and regenerate AI responses from that point.
// ============================================================================

import { protectMath, restoreMath } from '../utils/math.js';
import Logger from '../core/logger.js';

/**
 * Convert <tool_call> XML blocks to renderable markdown.
 * - code_display → fenced code block
 * - all others → stripped entirely
 */
export function preprocessToolCalls(text) {
    if (!text || !text.includes('<tool_call')) return text;

    // code_display (complete) → fenced code block
    // Handles proper </tool_call>, malformed <tool_call> closing, AND missing closing tag
    text = text.replace(
        /<tool_call\s+name="code_display"[^>]*>\s*<language>([^<]*)<\/language>\s*<code>([\s\S]*?)<\/code>(?:\s*<execute>[^<]*<\/execute>)?(?:\s*<\/?tool_call\s*>)?/gi,
        (_, lang, code) => '\n```' + (lang || 'text') + '\n' + code.trim() + '\n```\n'
    );

    // In-progress code_display (no </code> yet, genuinely still streaming)
    text = text.replace(
        /<tool_call\s+name="code_display"[^>]*>\s*<language>([^<]*)<\/language>\s*<code>([\s\S]*)$/gi,
        (match, lang, rest) => {
            // Safety: if </code> exists, block is complete but was missed above
            const codeEndIdx = rest.indexOf('</code>');
            if (codeEndIdx >= 0) {
                const code = rest.substring(0, codeEndIdx);
                const after = rest.substring(codeEndIdx + 7);
                return '\n```' + (lang || 'text') + '\n' + code.trim() + '\n```\n' +
                       after.replace(/^\s*(?:<\/?tool_call[^>]*>)?\s*/, '');
            }
            return '\n```' + (lang || 'text') + '\n' + rest.trim() + '\n';
        }
    );

    // Strip other complete tool_call blocks
    text = text.replace(/<tool_call[^>]*>[\s\S]*?<\/tool_call>/gi, '');

    // Strip orphaned non-code tool_call tags and their immediate XML children
    // (e.g. <tool_call name="web_search"><query>...</query>) without eating prose after them
    text = text.replace(/<tool_call\s+name="(?!code_display)[^"]*"[^>]*>(?:\s*<[a-z_]+>[^<]*<\/[a-z_]+>)*\s*/gi, '');

    // Strip any remaining bare <tool_call> or </tool_call> tags (malformed remnants)
    text = text.replace(/<\/?\s*tool_call[^>]*>/gi, '');

    return text;
}

/**
 * Parse markdown with math protection.
 * Protects LaTeX from being mangled by marked.
 */
export function parseMarkdownWithMath(content) {
    let cleaned = preprocessToolCalls(content);
    const { processed, mathBlocks } = protectMath(cleaned);
    let html = marked.parse(processed);
    return restoreMath(html, mathBlocks);
}

/**
 * Add edit button to a user message element.
 * @param {HTMLElement} messageDiv - The message DOM element
 * @param {string} messageContent - The original message content
 * @param {number} userIndex - Optional: the index of this user message (0-based)
 * @param {function} onEditAndRegenerate - Callback: (msgIndex, newContent) => Promise
 */
export function addEditButton(messageDiv, messageContent, userIndex = null, onEditAndRegenerate = null) {
    // Calculate userIndex if not provided
    if (userIndex === null) {
        const allMessages = document.querySelectorAll('.message.user');
        userIndex = Array.from(allMessages).indexOf(messageDiv);
        if (userIndex === -1) {
            userIndex = document.querySelectorAll('.message.user').length - 1;
        }
    }

    // Store index as data attribute for reliable retrieval
    messageDiv.dataset.userIndex = userIndex;

    const btn = document.createElement('button');
    btn.className = 'edit-msg-btn';
    btn.innerHTML = '✎';
    btn.title = 'Edit message';
    btn.onclick = (e) => {
        e.stopPropagation();
        enterEditMode(messageDiv, messageContent, onEditAndRegenerate);
    };
    messageDiv.appendChild(btn);
}

/**
 * Enter edit mode for a user message.
 * @param {HTMLElement} messageDiv
 * @param {string} originalContent
 * @param {function} onEditAndRegenerate - Callback: (msgIndex, newContent) => Promise
 */
function enterEditMode(messageDiv, originalContent, onEditAndRegenerate) {
    messageDiv.dataset.originalContent = originalContent;

    const editContainer = document.createElement('div');
    editContainer.className = 'edit-container';
    editContainer.innerHTML = `
        <textarea class="edit-textarea">${originalContent}</textarea>
        <div class="edit-actions">
            <button class="edit-cancel-btn">Cancel</button>
            <button class="edit-save-btn">Save & Regenerate</button>
        </div>
    `;

    // Hide original content, show edit UI
    messageDiv.querySelector('.edit-msg-btn')?.remove();
    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'original-content';
    contentWrapper.style.display = 'none';
    contentWrapper.innerHTML = messageDiv.innerHTML;
    messageDiv.innerHTML = '';
    messageDiv.appendChild(contentWrapper);
    messageDiv.appendChild(editContainer);

    // Focus textarea
    const textarea = editContainer.querySelector('.edit-textarea');
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    // Cancel handler
    editContainer.querySelector('.edit-cancel-btn').onclick = () => {
        messageDiv.innerHTML = contentWrapper.innerHTML;
        addEditButton(messageDiv, originalContent, null, onEditAndRegenerate);
    };

    // Save & Regenerate handler
    editContainer.querySelector('.edit-save-btn').onclick = async () => {
        const newContent = textarea.value.trim();
        if (!newContent) return;

        const msgIndex = findMessageIndex(messageDiv);
        if (msgIndex >= 0 && onEditAndRegenerate) {
            await onEditAndRegenerate(msgIndex, newContent);
        }
    };
}

/**
 * Find message index in chat history by DOM element.
 * Uses data-user-index attribute for reliable retrieval.
 */
export function findMessageIndex(messageDiv) {
    // First try data attribute (most reliable)
    if (messageDiv.dataset.userIndex !== undefined) {
        const idx = parseInt(messageDiv.dataset.userIndex, 10);
        Logger.debug('Found user index from data attribute:', idx);
        return idx;
    }

    // Fallback: count user messages up to this one
    const messages = document.querySelectorAll('.message');
    let userIndex = -1;
    for (let i = 0; i < messages.length; i++) {
        if (messages[i].classList.contains('user')) {
            userIndex++;
        }
        if (messages[i] === messageDiv) {
            Logger.debug('Found user index by DOM traversal:', userIndex);
            return userIndex;
        }
    }
    Logger.warn('Could not find message index');
    return -1;
}
