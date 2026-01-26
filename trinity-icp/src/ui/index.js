// ui/index.js - UI module aggregator
// Combines all UI sub-modules into a single unified interface

import DOMCache from './domCache.js';
import Messages from './messages.js';
import Sidebar from './sidebar.js';
import Modals from './modals.js';
import Notifications from './notifications.js';

// Unified UI interface
const UI = {
    // DOM element cache
    elements: {},

    // Initialize all UI sub-modules
    init() {
        DOMCache.init();
        this.elements = DOMCache.elements;
        
        // Share DOM cache with sub-modules
        Messages.elements = this.elements;
        Sidebar.elements = this.elements;
    },

    // Message methods
    setGenerating(isGenerating, State) {
        return Messages.setGenerating(isGenerating, State);
    },
    
    showMessage(type, content, animate = false) {
        return Messages.showMessage(type, content, animate);
    },
    
    typeMessage(messageDiv, text) {
        return Messages.typeMessage(messageDiv, text);
    },
    
    removeMessage(id) {
        return Messages.removeMessage(id);
    },
    
    clearMessages() {
        return Messages.clearMessages();
    },
    
    showChatArea() {
        return Messages.showChatArea();
    },
    
    renderChatHistory(State) {
        return Messages.renderChatHistory(State);
    },
    
    resetInput() {
        return Messages.resetInput();
    },
    
    autoResize(textarea) {
        return Messages.autoResize(textarea);
    },
    
    handleKeyboardChange(State) {
        return Messages.handleKeyboardChange(State);
    },
    
    scrollToBottom() {
        return Messages.scrollToBottom();
    },
    
    updateConnectionStatus(connected, healthData, errorDetail) {
        return Messages.updateConnectionStatus(connected, healthData, errorDetail);
    },
    
    showEnvironmentSwitcher(Actions) {
        return Messages.showEnvironmentSwitcher(Actions);
    },
    
    switchToEnvironment(env, activeBtn, inactiveBtn, Actions) {
        return Messages.switchToEnvironment(env, activeBtn, inactiveBtn, Actions);
    },
    
    setLoading(isLoading, State) {
        return Messages.setLoading(isLoading, State);
    },

    // Sidebar methods
    renderSidebar(State) {
        return Sidebar.renderSidebar(State);
    },

    // Modal methods
    showConfirmDialog(title, message) {
        return Modals.showConfirmDialog(title, message);
    },
    
    showPrompt(title, message, buttonText, callback) {
        return Modals.showPrompt(title, message, buttonText, callback);
    },
    
    showInputDialog(prompt) {
        return Modals.showInputDialog(prompt);
    },

    // Notification methods
    showAutosaveIndicator(status) {
        return Notifications.showAutosaveIndicator(status);
    },
    
    hideAutosaveIndicator() {
        return Notifications.hideAutosaveIndicator();
    },
    
    showSummarizationIndicator() {
        return Notifications.showSummarizationIndicator();
    },
    
    showError(message) {
        return Notifications.showError(message);
    },
    
    showSuccess(message) {
        return Notifications.showSuccess(message);
    },
    
    showWarning(message) {
        return Notifications.showWarning(message);
    },
    
    showNotification(message, type = 'info') {
        return Notifications.showNotification(message, type);
    },
    
    // UI state control
    disableUI() {
        const appContainer = document.querySelector('.app-container');
        const promptInput = document.getElementById('promptInput');
        const sendBtn = document.getElementById('sendBtn');
        
        if (appContainer) {
            appContainer.classList.add('ui-disabled');
        }
        if (promptInput) {
            promptInput.disabled = true;
            promptInput.placeholder = 'Please authenticate to use Trinity...';
        }
        if (sendBtn) {
            sendBtn.disabled = true;
        }
    },
    
    enableUI() {
        const appContainer = document.querySelector('.app-container');
        const promptInput = document.getElementById('promptInput');
        const sendBtn = document.getElementById('sendBtn');
        
        if (appContainer) {
            appContainer.classList.remove('ui-disabled');
        }
        if (promptInput) {
            promptInput.disabled = false;
            promptInput.placeholder = 'Ask anything...';
        }
        if (sendBtn) {
            sendBtn.disabled = false;
        }
    }
};

export default UI;
