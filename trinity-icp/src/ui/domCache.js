// domCache.js - DOM element caching and initialization
// Responsible for caching frequently-accessed DOM elements

const DOMCache = {
    // Cached DOM elements (populated in init)
    elements: {},

    init() {
        this.elements = {
            messagesContainer: document.getElementById('messagesContainer'),
            emptyState: document.getElementById('emptyState'),
            promptInput: document.getElementById('promptInput'),
            sendBtn: document.getElementById('sendBtn'),
            chatArea: document.getElementById('chatArea'),
            sidebar: document.getElementById('sidebar'),
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            // New status panel elements
            statusPanel: document.getElementById('statusPanel'),
            infraStack: document.getElementById('infraStack'),
            akashIndicator: document.getElementById('akashIndicator'),
            icpIndicator: document.getElementById('icpIndicator'),
            ipfsIndicator: document.getElementById('ipfsIndicator'),
            modelName: document.getElementById('modelName'),
            modelBadge: document.getElementById('modelBadge'),
            logoutBtn: document.getElementById('logoutBtn'),
            // Legacy (kept for compatibility)
            providerInfo: document.getElementById('providerInfo'),
            modelInfo: document.getElementById('modelInfo'),
            inputContainer: document.getElementById('inputContainer'),
            toggleSidebarBtn: document.querySelector('.toggle-sidebar-btn'),
            sidebarToggleBtn: document.querySelector('.sidebar .toggle-btn'),
            attachBtn: document.querySelector('.attach-btn')
        };
    }
};

export default DOMCache;
