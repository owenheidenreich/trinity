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
