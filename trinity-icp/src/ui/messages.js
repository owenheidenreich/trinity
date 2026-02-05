// messages.js - Message rendering and chat display
// Responsible for displaying messages, typing animations, and chat history

import CONFIG from '../config.js';
import { renderMath, protectMath, restoreMath } from '../utils/math.js';

/**
 * Parse markdown content with math protection
 * Protects math expressions from being mangled by markdown parser
 */
function parseMarkdownWithMath(content) {
    // Protect math expressions from markdown parsing
    const { processed, mathBlocks } = protectMath(content);
    
    // Parse markdown
    let html = marked.parse(processed);
    
    // Restore math expressions
    html = restoreMath(html, mathBlocks);
    
    return html;
}

/**
 * Enhance code blocks with copy button, language label, and syntax highlighting
 * @param {HTMLElement} container - The container to search for code blocks
 */
function enhanceCodeBlocks(container) {
    const codeBlocks = container.querySelectorAll('pre code');
    
    codeBlocks.forEach(codeElement => {
        const pre = codeElement.parentElement;
        
        // Skip if already enhanced
        if (pre.classList.contains('enhanced')) return;
        pre.classList.add('enhanced');
        
        // IMPORTANT: Store code text BEFORE any DOM manipulation
        const codeText = codeElement.textContent;
        
        // Apply syntax highlighting with highlight.js
        if (typeof hljs !== 'undefined') {
            // Remove any existing hljs classes to allow re-highlighting
            codeElement.classList.remove('hljs');
            hljs.highlightElement(codeElement);
        }
        
        // Detect language from class (e.g., "language-python" or "hljs language-python")
        const langClass = Array.from(codeElement.classList).find(c => c.startsWith('language-'));
        const language = langClass ? langClass.replace('language-', '') : 'code';
        
        // Create header with language label and copy button
        const header = document.createElement('div');
        header.className = 'code-block-header';
        header.innerHTML = `
            <span class="code-language">${language}</span>
            <button class="code-copy-btn" title="Copy code">Copy</button>
        `;
        
        // Insert header before the pre element
        pre.parentNode.insertBefore(header, pre);
        
        // Wrap header and pre in a container
        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrapper';
        header.parentNode.insertBefore(wrapper, header);
        wrapper.appendChild(header);
        wrapper.appendChild(pre);
        
        // Add copy functionality using stored codeText (not live DOM reference)
        const copyBtn = header.querySelector('.code-copy-btn');
        copyBtn.addEventListener('click', () => {
            try {
                // Use textarea selection method (Clipboard API blocked by ICP permissions policy)
                const textArea = document.createElement('textarea');
                textArea.value = codeText;
                textArea.style.position = 'fixed';
                textArea.style.top = '0';
                textArea.style.left = '0';
                textArea.style.width = '2em';
                textArea.style.height = '2em';
                textArea.style.padding = '0';
                textArea.style.border = 'none';
                textArea.style.outline = 'none';
                textArea.style.boxShadow = 'none';
                textArea.style.background = 'transparent';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();

                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);

                if (!successful) {
                    throw new Error('execCommand copy failed');
                }

                copyBtn.textContent = 'Copied!';
                copyBtn.classList.add('copied');
                setTimeout(() => {
                    copyBtn.textContent = 'Copy';
                    copyBtn.classList.remove('copied');
                }, 2000);
            } catch (err) {
                console.error('Failed to copy:', err);
                copyBtn.textContent = 'Failed';
                setTimeout(() => {
                    copyBtn.textContent = 'Copy';
                }, 2000);
            }
        });
    });
}

const Messages = {
    // Reference to DOM cache (will be set by UI module)
    elements: null,

    // Set generating state (disables input, shows stop button)
    setGenerating(isGenerating, State) {
        const { sendBtn, promptInput } = this.elements;
        State.setGenerating(isGenerating);

        // CRITICAL: Remove ui-disabled class if present (it blocks pointer events with pointer-events: none)
        const appContainer = document.querySelector('.app-container');
        if (appContainer && appContainer.classList.contains('ui-disabled')) {
            console.warn('⚠️ Removing stale ui-disabled class during generation');
            appContainer.classList.remove('ui-disabled');
        }

        // Keep button enabled during generation so user can stop
        sendBtn.disabled = false;
        promptInput.disabled = isGenerating;

        if (isGenerating) {
            sendBtn.classList.add('generating');
            sendBtn.textContent = '■';  // Visible stop icon (not CSS ::before)
            sendBtn.title = 'Stop generation';
            sendBtn.dataset.action = 'stop';
        } else {
            sendBtn.classList.remove('generating');
            sendBtn.textContent = '➤';
            sendBtn.title = 'Send message';
            sendBtn.dataset.action = 'send';
            promptInput.focus();
        }
    },

    // Add a message to the chat (optionally with typing animation)
    showMessage(type, content, animate = false) {
        const { messagesContainer } = this.elements;
        const messageDiv = document.createElement('div');
        const messageId = 'msg-' + Date.now();
        messageDiv.id = messageId;
        messageDiv.className = `message ${type}`;

        if (animate && type === 'ai') {
            messagesContainer.appendChild(messageDiv);
            this.typeMessage(messageDiv, content);
            return messageId;
        }

        if (type === 'ai' && !content.includes('loading-dots')) {
            messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(content));
            // Render math expressions after DOM insertion
            renderMath(messageDiv);
            // Enhance code blocks with copy button
            enhanceCodeBlocks(messageDiv);
        } else if (content.includes('loading-dots')) {
            // Loading indicator - safe static HTML
            messageDiv.innerHTML = DOMPurify.sanitize(content, { ADD_TAGS: ['span'], ADD_ATTR: ['class'] });
        } else {
            // User messages - sanitize but allow markdown/math rendering
            messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(content));
            renderMath(messageDiv);
            enhanceCodeBlocks(messageDiv);
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        return messageId;
    },

    // Typing animation for AI responses
    async typeMessage(messageDiv, text) {
        const { chatArea } = this.elements;
        const maxTime = CONFIG.TYPE_ANIMATION_MAX_MS;
        const baseSpeed = CONFIG.TYPE_BASE_SPEED_MS;
        const speed = Math.min(baseSpeed, maxTime / text.length);
        const charsPerFrame = text.length > 1000 ? 5 : 1;

        for (let i = 0; i < text.length; i += charsPerFrame) {
            const current = text.substring(0, i + charsPerFrame);
            messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(current));
            chatArea.scrollTop = chatArea.scrollHeight;

            if (speed > 2) {
                await new Promise(r => setTimeout(r, speed));
            } else {
                await new Promise(r => requestAnimationFrame(r));
            }
        }

        // Final render to ensure complete
        messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(text));
        // Render math after final content is set
        renderMath(messageDiv);
        // Enhance code blocks with copy button
        enhanceCodeBlocks(messageDiv);
        chatArea.scrollTop = chatArea.scrollHeight;
        return messageDiv.id;
    },

    // Remove a message by ID
    removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    },

    // Clear all messages and show empty state
    clearMessages() {
        this.elements.messagesContainer.innerHTML = '';
        this.elements.messagesContainer.classList.remove('active');
        this.elements.emptyState.style.display = 'flex';
    },

    // Show the chat area (hide empty state)
    showChatArea() {
        this.elements.emptyState.style.display = 'none';
        this.elements.messagesContainer.classList.add('active');
    },

    // Render chat history from State to DOM
    renderChatHistory(State) {
        const { messagesContainer, chatArea } = this.elements;
        messagesContainer.innerHTML = '';

        if (State.chatHistory.length > 0) {
            this.showChatArea();
            State.setChatStarted(true);

            State.chatHistory.forEach(msg => {
                this.showMessage(msg.role === 'assistant' ? 'ai' : 'user', msg.content);
            });

            chatArea.scrollTop = chatArea.scrollHeight;
        }
    },

    // Reset input field and re-enable it
    // NOTE: Does NOT touch sendBtn.disabled - let setGenerating() manage button state
    resetInput() {
        const { promptInput } = this.elements;
        promptInput.value = '';
        promptInput.disabled = false;  // Always re-enable on reset
        // DON'T disable sendBtn here - it breaks the stop button during generation
        // autoResize() will handle enabling/disabling based on input content
        this.autoResize(promptInput);
        promptInput.focus();
    },

    // Auto-resize textarea
    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
        // Don't disable the stop button during generation!
        const isStopMode = this.elements.sendBtn.dataset.action === 'stop';
        if (!isStopMode) {
            this.elements.sendBtn.disabled = !textarea.value.trim();
        }
    },

    // Handle mobile keyboard visibility
    handleKeyboardChange(State) {
        if (!window.visualViewport) return;

        const currentHeight = window.visualViewport.height;
        const { inputContainer, promptInput } = this.elements;

        if (currentHeight < State.initialViewportHeight * CONFIG.KEYBOARD_THRESHOLD) {
            if (!State.keyboardOpen) {
                State.setKeyboardOpen(true);
                inputContainer.classList.add('keyboard-open');
                setTimeout(() => {
                    promptInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 100);
            }
        } else {
            if (State.keyboardOpen) {
                State.setKeyboardOpen(false);
                inputContainer.classList.remove('keyboard-open');
            }
        }
    },

    // Scroll messages to bottom
    scrollToBottom() {
        const { messagesContainer, promptInput } = this.elements;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        promptInput.scrollIntoView({ block: 'end' });
    },

    // Update connection status display
    updateConnectionStatus(connected, healthData, errorDetail) {
        const { 
            statusDot, statusText, 
            akashIndicator, icpIndicator, ipfsIndicator,
            modelName, modelBadge,
            providerInfo, modelInfo // Legacy fallback
        } = this.elements;

        if (!statusDot || !statusText) {
            console.warn('Status elements not found');
            return;
        }

        // Always attach infrastructure modal handlers (regardless of connection state)
        const gpuType = healthData?.gpu_type || 'GPU';
        const model = healthData?.model || 'Unknown';
        
        const akashStatus = document.getElementById('akashStatus');
        if (akashStatus && !akashStatus._handlerAttached) {
            akashStatus._handlerAttached = true;
            akashStatus.onclick = (e) => {
                e.preventDefault();
                import('./modals.js').then(({ default: Modals }) => {
                    Modals.showAkashProviderModal('provider.akashprovid.com', gpuType, model);
                });
            };
        }
        
        const icpStatus = document.getElementById('icpStatus');
        if (icpStatus && !icpStatus._handlerAttached) {
            icpStatus._handlerAttached = true;
            icpStatus.onclick = (e) => {
                e.preventDefault();
                import('./modals.js').then(({ default: Modals }) => {
                    Modals.showICPModal('zc67k-kiaaa-aaaal-qtmiq-cai');
                });
            };
        }
        
        const ipfsStatus = document.getElementById('ipfsStatus');
        if (ipfsStatus && !ipfsStatus._handlerAttached) {
            ipfsStatus._handlerAttached = true;
            ipfsStatus.onclick = (e) => {
                e.preventDefault();
                import('./modals.js').then(({ default: Modals }) => {
                    Modals.showIPFSStorageModal();
                });
            };
        }

        if (connected && healthData) {
            statusDot.classList.remove('disconnected');
            statusDot.classList.add('connected');
            statusText.textContent = 'Connected';
            
            // Update status indicators
            if (icpIndicator) icpIndicator.textContent = '●';
            if (akashIndicator) akashIndicator.textContent = '●';
            if (ipfsIndicator) ipfsIndicator.textContent = '●';
            
            // Update model name
            if (modelName) {
                modelName.textContent = model;
            }
            
            // Model modal handler
            if (modelBadge && !modelBadge._handlerAttached) {
                modelBadge._handlerAttached = true;
                modelBadge.onclick = (e) => {
                    e.preventDefault();
                    import('./modals.js').then(({ default: Modals }) => {
                        Modals.showModelModal(model, gpuType);
                    });
                };
            }
            
            // Legacy support
            if (CONFIG._currentEnvironment === 'local') {
                if (providerInfo) providerInfo.innerHTML = '<span style="color: #f0ad4e;">⚠️ Local Dev</span>';
                if (modelInfo) modelInfo.textContent = `Model: ${model}`;
            }
            
            console.log('✅ Status updated: Connected to', healthData.provider_id, healthData.model);
        } else {
            statusDot.classList.remove('connected');
            statusDot.classList.add('disconnected');
            statusText.textContent = 'Disconnected';
            
            // Update status indicators to show offline
            if (icpIndicator) icpIndicator.textContent = '○';
            if (akashIndicator) akashIndicator.textContent = '○';
            if (ipfsIndicator) ipfsIndicator.textContent = '○';
            
            if (modelName) modelName.textContent = 'Offline';
            
            // Legacy support
            if (providerInfo) providerInfo.textContent = errorDetail || 'Check Akash deployment';
            if (modelInfo) modelInfo.textContent = `URL: ${CONFIG.API_URL}`;
            console.warn('⚠️ Status updated: Disconnected');
        }
    },
    
    // Show environment switcher if both local and production are available
    showEnvironmentSwitcher(Actions) {
        const statusInfo = document.getElementById('statusInfo');
        if (!statusInfo) return;
        
        // Check if switcher already exists
        if (document.getElementById('envSwitcher')) return;
        
        const switcher = document.createElement('div');
        switcher.id = 'envSwitcher';
        switcher.style.cssText = 'margin-top: 8px; display: flex; gap: 4px; font-size: 11px;';
        
        const localBtn = document.createElement('button');
        localBtn.textContent = '🖥️ Local';
        localBtn.style.cssText = 'flex: 1; padding: 4px 8px; border-radius: 4px; border: 1px solid #444; background: #2a2a2a; color: #aaa; cursor: pointer; font-size: 11px;';
        localBtn.onclick = () => this.switchToEnvironment('local', localBtn, prodBtn, Actions);
        
        // Disable local button if not available
        if (!CONFIG._availableEnvironments.local) {
            localBtn.disabled = true;
            localBtn.style.opacity = '0.5';
            localBtn.style.cursor = 'not-allowed';
            localBtn.title = 'Local backend not running (start with ./dev.sh)';
        }
        
        const prodBtn = document.createElement('button');
        prodBtn.textContent = '☁️ Akash';
        prodBtn.style.cssText = 'flex: 1; padding: 4px 8px; border-radius: 4px; border: 1px solid #444; background: #2a2a2a; color: #aaa; cursor: pointer; font-size: 11px;';
        prodBtn.onclick = () => this.switchToEnvironment('production', prodBtn, localBtn, Actions);
        
        // Highlight current environment
        if (CONFIG._currentEnvironment === 'local') {
            localBtn.style.background = '#0a4d0a';
            localBtn.style.color = '#0f0';
            localBtn.style.borderColor = '#0f0';
        } else {
            prodBtn.style.background = '#0a4d0a';
            prodBtn.style.color = '#0f0';
            prodBtn.style.borderColor = '#0f0';
        }
        
        switcher.appendChild(localBtn);
        switcher.appendChild(prodBtn);
        statusInfo.appendChild(switcher);
        
        console.log('✅ Environment switcher added');
    },
    
    // Switch to different environment
    async switchToEnvironment(env, activeBtn, inactiveBtn, Actions) {
        console.log(`🔄 Switching to ${env} environment...`);
        
        if (!CONFIG.switchEnvironment(env)) {
            alert(`${env} environment not available`);
            return;
        }
        
        // Update button styles
        activeBtn.style.background = '#0a4d0a';
        activeBtn.style.color = '#0f0';
        activeBtn.style.borderColor = '#0f0';
        
        inactiveBtn.style.background = '#2a2a2a';
        inactiveBtn.style.color = '#aaa';
        inactiveBtn.style.borderColor = '#444';
        
        // Reconnect to new environment
        await Actions.checkConnection();
        
        console.log(`✅ Switched to ${env} environment`);
    },

    // Set loading state (alias for setGenerating)
    setLoading(isLoading, State) {
        this.setGenerating(isLoading, State);
    }
};

export { enhanceCodeBlocks };
export default Messages;
