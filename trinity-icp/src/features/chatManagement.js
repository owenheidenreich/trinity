// ============================================================================
// FEATURE: CHAT MANAGEMENT — Chat CRUD, sidebar, autosave, navigation
// ============================================================================
// Handles: new/load/delete/pin/export chats, autosave, sidebar toggle.
// ============================================================================

import API from '../core/api.js';
import Logger from '../core/logger.js';
import State from '../state/store.js';
import UI from '../ui/index.js';
import AutosaveManager from '../storage/autosave.js';
import { addEditButton } from '../ui/editMessage.js';

/**
 * Start a new chat.
 */
export function newChat() {
    if (!State.isAuthenticated) {
        Logger.warn('New chat blocked - user not authenticated');
        return;
    }

    UI.clearMessages();
    UI.resetInput();
    State.reset();

    if (UI.elements.promptInput) {
        UI.elements.promptInput.disabled = false;
    }
    if (UI.elements.submitButton) {
        UI.elements.submitButton.disabled = true;
    }

    const attachBtn = document.getElementById('attachBtn');
    if (attachBtn) attachBtn.disabled = false;

    const chatArea = document.getElementById('chatArea');
    if (chatArea) chatArea.scrollTop = 0;

    UI.renderSidebar(State);
    Logger.debug('New chat started');
}

/**
 * Toggle sidebar visibility.
 */
export function toggleSidebar() {
    const sidebar = UI.elements.sidebar;
    const wasCollapsed = sidebar.classList.contains('collapsed');
    sidebar.classList.toggle('collapsed');

    if (window.innerWidth <= 768) {
        if (wasCollapsed) {
            sidebar.classList.add('mobile-open');
            setTimeout(() => {
                document.addEventListener('click', closeSidebarOnClickOutside);
            }, 10);
        } else {
            sidebar.classList.remove('mobile-open');
            document.removeEventListener('click', closeSidebarOnClickOutside);
        }
    }
}

/**
 * Close sidebar when clicking outside (mobile).
 */
export function closeSidebarOnClickOutside(event) {
    const sidebar = UI.elements.sidebar;
    const toggleBtn = UI.elements.toggleSidebarBtn;
    const sidebarToggleBtn = UI.elements.sidebarToggleBtn;

    if (!sidebar.contains(event.target) &&
        !toggleBtn?.contains(event.target) &&
        !sidebarToggleBtn?.contains(event.target)) {
        sidebar.classList.add('collapsed');
        sidebar.classList.remove('mobile-open');
        document.removeEventListener('click', closeSidebarOnClickOutside);
    }
}

/**
 * Handle Enter key in input.
 * @param {KeyboardEvent} event
 * @param {function} generateFn - The generate function to call
 */
export function handleKeyDown(event, generateFn) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (event.target.value.trim()) {
            generateFn();
        }
    }
}

/**
 * Load all chats for authenticated user.
 */
export async function loadChats() {
    if (!State.isAuthenticated) {
        Logger.debug('loadChats() skipped - not authenticated');
        return;
    }

    try {
        Logger.debug('Loading chats...');
        const response = await API.listChats();
        const chats = response.chats || [];

        Logger.debug('Chats loaded:', chats.length);
        State.setAllChats(chats);
        UI.renderSidebar(State);
    } catch (error) {
        Logger.error('Failed to load chats:', error);
    }
}

/**
 * Execute autosave (wrapper for AutosaveManager).
 */
export async function executeAutosave() {
    const result = await AutosaveManager.executeAutosave({
        currentChatId: State.currentChatId,
        chatHistory: State.chatHistory,
        isAuthenticated: State.isAuthenticated,
        principal: State.principal,
        apiSave: (chatData) => API.autosave(chatData),
        showIndicator: UI.showAutosaveIndicator,
        hideIndicator: UI.hideAutosaveIndicator,
        retryCallback: () => executeAutosave()
    });

    if (result.success) {
        State.setAutosaveStatus(result.autosaveStatus);
        State.setUnsavedChanges(result.unsavedChanges);
    } else if (result.autosaveStatus) {
        State.setAutosaveStatus(result.autosaveStatus);
    }

    return result;
}

/**
 * Load user memory (persistent facts).
 */
export async function loadUserMemory() {
    if (!State.isAuthenticated) {
        Logger.debug('loadUserMemory() skipped - not authenticated');
        return;
    }

    try {
        Logger.debug('Loading user memory...');
        const memory = await API.getUserMemory();
        State.setUserMemory(memory);
        Logger.debug(`User memory loaded: ${memory.facts?.length || 0} facts`);
    } catch (error) {
        Logger.error('Failed to load user memory:', error);
        State.setUserMemory({ facts: [], preferences: {} });
    }
}

/**
 * Load specific chat by ID.
 * @param {function} editAndRegenerate - Callback for edit-and-regenerate
 */
export async function loadChat(chatId, editAndRegenerate = null) {
    if (State.isLoadingChat) {
        Logger.debug('Already loading a chat, ignoring click');
        return;
    }

    if (!State.isAuthenticated) {
        Logger.warn('Load chat blocked - user not authenticated');
        return;
    }

    State.setLoadingChat(true);
    const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
    if (chatItem) chatItem.classList.add('loading');

    try {
        const response = await API.loadChat(chatId);
        const chatData = response;

        State.setChatHistory(chatData.messages || []);
        State.setCurrentChatId(chatData.chatId || chatId);
        State.setChatStarted(true);

        // Rebuild context memory from last messages
        State.setContextMemory([]);
        const recentMessages = State.chatHistory.slice(-State.CONTEXT_WINDOW_SIZE);
        recentMessages.forEach(msg => State.updateContextMemory(msg));
        Logger.debug(`Loaded chat with ${State.chatHistory.length} messages, context: ${State.contextMemory.length}`);

        UI.renderChatHistory(State);

        // Add edit buttons to user messages
        const userMessages = document.querySelectorAll('.message.user');
        let userIndex = 0;
        State.chatHistory.forEach((msg) => {
            if (msg.role === 'user' && userMessages[userIndex]) {
                const msgDiv = userMessages[userIndex];
                if (!msgDiv.querySelector('.edit-msg-btn')) {
                    addEditButton(msgDiv, msg.content, userIndex, editAndRegenerate);
                }
                userIndex++;
            }
        });

        if (UI.elements.promptInput) UI.elements.promptInput.disabled = false;
        if (UI.elements.submitButton) UI.elements.submitButton.disabled = false;

        const attachBtn = document.getElementById('attachBtn');
        if (attachBtn) attachBtn.disabled = false;
    } catch (error) {
        UI.showError('Failed to load chat: ' + error.message);
    } finally {
        State.setLoadingChat(false);
        if (chatItem) chatItem.classList.remove('loading');
    }
}

/**
 * Export chat as Markdown file.
 */
export async function exportChatAsMarkdown(chatId) {
    let chatHistory, title;

    if (chatId) {
        try {
            const chatData = await API.loadChat(chatId);
            if (!chatData || !chatData.messages || chatData.messages.length === 0) {
                UI.showNotification('Chat has no messages to export', 'warning');
                return;
            }
            chatHistory = chatData.messages;
            title = chatData.title || 'Trinity Chat';
        } catch (error) {
            UI.showNotification('Failed to load chat for export', 'error');
            return;
        }
    } else {
        if (State.chatHistory.length === 0) {
            UI.showNotification('No messages to export', 'warning');
            return;
        }
        chatHistory = State.chatHistory;
        title = State.currentChatTitle || 'Trinity Chat';
    }

    const date = new Date().toISOString().split('T')[0];

    let markdown = `# ${title}\n\n`;
    markdown += `> Exported from Trinity on ${new Date().toLocaleString()}\n\n---\n\n`;

    chatHistory.forEach((msg, index) => {
        const role = msg.role === 'user' ? '**You**' : '**Trinity**';
        markdown += `### ${role}\n\n`;
        markdown += `${msg.content}\n\n`;
        if (index < chatHistory.length - 1) {
            markdown += `---\n\n`;
        }
    });

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/[^a-z0-9]/gi, '-').toLowerCase()}-${date}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    UI.showNotification('Chat exported!', 'success');
}

/**
 * Delete chat.
 */
export async function deleteChat(chatId) {
    const chat = State.allChats.find(c => c.chatId === chatId);
    if (chat && chat.pinned) {
        UI.showWarning('Cannot delete a saved chat. Unsave it first.');
        return;
    }

    const confirmed = await UI.showConfirmDialog(
        'Delete chat?',
        'This action cannot be undone.'
    );

    if (!confirmed) return;

    try {
        await API.deleteChat(chatId);

        State.setAllChats(State.allChats.filter(c => c.chatId !== chatId));
        if (State.currentChatId === chatId) {
            newChat();
        }
        UI.renderSidebar(State);
        UI.showSuccess('Chat deleted');
    } catch (error) {
        UI.showError('Failed to delete chat: ' + error.message);
    }
}

/**
 * Pin/unpin chat.
 */
export async function pinChat(chatId) {
    try {
        const result = await API.request(`/chat/${chatId}/pin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });

        const updatedChats = State.allChats.map(c => {
            if (c.chatId === chatId) {
                return { ...c, pinned: result.pinned };
            }
            return c;
        });
        State.setAllChats(updatedChats);
        UI.renderSidebar(State);
        UI.showSuccess(result.pinned ? 'Chat saved' : 'Chat unsaved');
    } catch (error) {
        UI.showError('Failed to pin chat: ' + error.message);
    }
}

/**
 * Load user data in background (non-blocking, errors don't break auth).
 */
export async function loadUserDataInBackground() {
    Logger.debug('Loading user data in background...');

    try { await loadChats(); }
    catch (error) { Logger.warn('Failed to load chats (will retry later):', error.message); }

    try { await loadUserMemory(); }
    catch (error) { Logger.warn('Failed to load user memory (will retry later):', error.message); }

    // Retry pending syncs from IndexedDB
    try {
        const { synced } = await AutosaveManager.retryPendingSync(
            (chatData) => API.autosave(chatData)
        );
        if (synced > 0) {
            Logger.debug(`Synced ${synced} pending chat(s)`);
        }
    } catch (error) {
        Logger.warn('Failed to retry pending syncs:', error.message);
    }

    UI.renderSidebar(State);
    Logger.debug('Background data loading complete');
}
