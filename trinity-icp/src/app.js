// ============================================================================
// TRINITY FRONTEND — Application Orchestrator
// ============================================================================
// Thin entry point: imports feature modules, composes Actions, wires events.
// Business logic lives in features/, API in core/, UI in ui/.
// ============================================================================

import CONFIG from './config.js';
import UI from './ui/index.js';
import Modals from './ui/modals.js';
import AuthManager from './auth/authManager.js';
import AutosaveManager from './storage/autosave.js';
import State from './state/store.js';
import initRainbowBorders from './ui/rainbowBorder.js';
import { initTools } from './tools.js';

// Core modules
import API from './core/api.js';
import { detectEnvironment } from './core/environment.js';

// Feature modules
import { generate, stopGeneration, editAndRegenerate, checkConnection } from './features/generate.js';
import { initAuth, logout, exportKey } from './features/auth.js';
import {
    newChat, toggleSidebar, closeSidebarOnClickOutside, handleKeyDown,
    loadChats, loadChat, deleteChat, pinChat, executeAutosave,
    exportChatAsMarkdown, loadUserDataInBackground
} from './features/chatManagement.js';
import { viewMemory, addMemoryFact, deleteMemoryFact, openStatusDashboard } from './features/memory.js';

// ============================================================================
// ACTIONS — Composed from feature modules
// ============================================================================
const Actions = {
    // Generate & streaming
    generate:          () => generate(executeAutosave),
    stopGeneration,
    editAndRegenerate,
    checkConnection,

    // Authentication
    initAuth,
    logout,
    exportKey,

    // Chat management
    newChat,
    toggleSidebar,
    closeSidebarOnClickOutside,
    handleKeyDown:     (e) => handleKeyDown(e, () => Actions.generate()),
    loadChats,
    loadChat:          (chatId) => loadChat(chatId, editAndRegenerate),
    deleteChat,
    pinChat,
    executeAutosave,
    exportChatAsMarkdown,

    // Memory & status
    viewMemory,
    addMemoryFact,
    deleteMemoryFact,
    openStatusDashboard,
};

// ============================================================================
// INITIALIZATION
// ============================================================================
async function init() {
    console.log('🚀 Trinity initializing...');

    // Version check (cache bust)
    if (!CONFIG.checkVersion()) {
        console.log('🔄 Version update detected, reloading...');
        return;
    }

    // Initialize UI element cache
    UI.init();
    
    console.log('✅ UI initialized');

    // Detect environment (dev vs production)
    let isDevelopment = false;
    try {
        isDevelopment = await detectEnvironment();
        console.log('✅ Environment detected:', CONFIG.API_URL);
    } catch (error) {
        console.error('❌ Environment detection failed:', error);
        CONFIG.setAPIURL(CONFIG.API_URL, false);
    }

    // Show environment switcher in dev mode
    if (isDevelopment && CONFIG._availableEnvironments.production) {
        UI.showEnvironmentSwitcher(Actions);
    }

    // Render sidebar, set up autosave callback
    UI.renderSidebar(State);
    AutosaveManager.onSaveSuccess = () => Actions.loadChats();

    // Block UI until authenticated
    UI.disableUI();
    await Actions.initAuth();
    UI.enableUI();
    console.log('✅ User authenticated');

    // Configure marked.js
    marked.setOptions({
        highlight: (code, lang) => {
            if (lang && hljs.getLanguage(lang)) {
                try { return hljs.highlight(code, { language: lang }).value; } catch {}
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true,
        gfm: true
    });

    // -------------------- Event Listeners --------------------
    UI.elements.sendBtn.addEventListener('click', () => {
        const isStopMode = State.isGenerating || UI.elements.sendBtn.dataset.action === 'stop';
        isStopMode ? Actions.stopGeneration() : Actions.generate();
    });

    UI.elements.promptInput.addEventListener('keydown', (e) => Actions.handleKeyDown(e));
    UI.elements.promptInput.addEventListener('input', (e) => UI.autoResize(e.target));
    UI.elements.promptInput.addEventListener('focus', () => setTimeout(() => UI.handleKeyboardChange(State), 300));
    UI.elements.promptInput.addEventListener('blur', () => setTimeout(() => UI.handleKeyboardChange(State), 300));

    if (UI.elements.toggleSidebarBtn) UI.elements.toggleSidebarBtn.addEventListener('click', () => Actions.toggleSidebar());
    if (UI.elements.sidebarToggleBtn) UI.elements.sidebarToggleBtn.addEventListener('click', () => Actions.toggleSidebar());
    if (UI.elements.logoutBtn) UI.elements.logoutBtn.addEventListener('click', () => Actions.logout());

    const cidLink = document.getElementById('cidLink');
    if (cidLink) {
        cidLink.addEventListener('click', (e) => {
            e.preventDefault();
            const cid = cidLink.dataset.cid;
            if (cid) Modals.showIPFSModal(cid);
        });
    }

    window.addEventListener('resize', () => {
        if (window.innerWidth <= 768) UI.elements.sidebar.classList.add('collapsed');
    });

    // -------------------- Event Delegation --------------------
    document.addEventListener('click', (e) => {
        let parent = e.target;
        while (parent) {
            if (parseInt(window.getComputedStyle(parent).zIndex) >= 10000) return;
            parent = parent.parentElement;
        }

        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        e.stopPropagation();

        const { action, chatId, factIndex } = btn.dataset;

        if (action === 'loadChat' && chatId) Actions.loadChat(chatId);
        else if (action === 'deleteChat' && chatId) Actions.deleteChat(chatId);
        else if (action === 'pinChat' && chatId) Actions.pinChat(chatId);
        else if (action === 'newChat') Actions.newChat();
        else if (action === 'exportChat' && chatId) {
            if (btn._isExporting) return;
            btn._isExporting = true;
            Actions.exportChatAsMarkdown(chatId).finally(() => { btn._isExporting = false; });
        }
        else if (action === 'logout') Actions.logout();
        else if (action === 'exportKey') Actions.exportKey();
        else if (action === 'viewMemory') Actions.viewMemory();
        else if (action === 'addNewFact') {
            const fact = document.getElementById('newFactInput')?.value?.trim();
            if (fact) Actions.addMemoryFact(fact);
        }
        else if (action === 'deleteFact' && factIndex !== undefined) Actions.deleteMemoryFact(parseInt(factIndex));
        else if (action === 'closeMemoryDialog' || action === 'closeStatusDialog') {
            btn.closest('.modal-dialog')?.remove();
        }
        else if (action === 'openStatus') Actions.openStatusDashboard();
        else if (action === 'showAbout') Modals.showAboutModal();
    });

    // Chat item hover effects
    document.addEventListener('mouseover', (e) => {
        const item = e.target.closest('.chat-item');
        if (!item) return;
        item.style.background = '#3d3d3d';
        const del = item.querySelector('.delete-btn');
        if (del) del.style.display = 'inline-block';
    });
    document.addEventListener('mouseout', (e) => {
        const item = e.target.closest('.chat-item');
        if (!item) return;
        item.style.background = '#2d2d2d';
        const del = item.querySelector('.delete-btn');
        if (del) del.style.display = 'none';
    });

    // Mobile keyboard handling
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => UI.handleKeyboardChange(State));
        window.visualViewport.addEventListener('scroll', () => UI.handleKeyboardChange(State));
        window.visualViewport.addEventListener('resize', () => UI.scrollToBottom());
    }

    // Initialize plugins
    initRainbowBorders();
    initTools();

    // Collapse sidebar on mobile at startup
    if (window.innerWidth <= 768) {
        UI.elements.sidebar.classList.add('no-transition', 'collapsed');
        setTimeout(() => UI.elements.sidebar.classList.remove('no-transition'), 100);
    }

    console.log('✅ Trinity fully initialized');

    // Health checks
    setTimeout(() => Actions.checkConnection(), 100);
    State.setHealthCheckInterval(setInterval(() => Actions.checkConnection(), CONFIG.HEALTH_CHECK_INTERVAL_MS));
}

// ============================================================================
// BOOTSTRAP
// ============================================================================
document.addEventListener('DOMContentLoaded', init);

window.addEventListener('autosave-error', (e) => {
    const { message, final } = e.detail || {};
    final
        ? UI.showError(message || 'Save failed. Your chat is preserved locally.')
        : UI.showWarning(message || 'Save delayed — will retry automatically.');
});

// ============================================================================
// EXPORTS
// ============================================================================
window.State = State;
window.API = API;
window.UI = UI;
window.Actions = Actions;

export { State, API, UI, Actions };

// Legacy globals (being phased out)
window.toggleSidebar = () => Actions.toggleSidebar();
window.newChat = () => Actions.newChat();
window.logout = () => Actions.logout();
window.exportKey = () => Actions.exportKey();
window.viewMemory = () => Actions.viewMemory();
window.generate = () => Actions.generate();
window.handleKeyDown = (e) => Actions.handleKeyDown(e);
window.autoResize = (el) => UI.autoResize(el);
window.loadChat = (chatId) => Actions.loadChat(chatId);
window.deleteChat = (chatId) => Actions.deleteChat(chatId);

// Debug helpers
window.debugAuth = () => {
    console.log('=== AUTH DEBUG ===');
    console.log('AuthManager.isInitialized:', AuthManager.isInitialized);
    console.log('State.isAuthenticated:', State.isAuthenticated);
    console.log('State.principal:', State.principal);
    console.log('=================');
};
