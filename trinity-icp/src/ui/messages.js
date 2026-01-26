// messages.js - Message rendering and chat display
// Responsible for displaying messages, typing animations, and chat history

import CONFIG from '../config.js';

const Messages = {
    // Reference to DOM cache (will be set by UI module)
    elements: null,

    // Set generating state (disables input, shows loading indicator)
    setGenerating(isGenerating, State) {
        const { sendBtn, promptInput } = this.elements;
        State.setGenerating(isGenerating);
        sendBtn.disabled = isGenerating;
        promptInput.disabled = isGenerating;

        if (isGenerating) {
            sendBtn.classList.add('generating');
            sendBtn.textContent = '';
        } else {
            sendBtn.classList.remove('generating');
            sendBtn.textContent = '➤';
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
            messageDiv.innerHTML = DOMPurify.sanitize(marked.parse(content));
        } else {
            messageDiv.innerHTML = content;
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
            messageDiv.innerHTML = DOMPurify.sanitize(marked.parse(current));
            chatArea.scrollTop = chatArea.scrollHeight;

            if (speed > 2) {
                await new Promise(r => setTimeout(r, speed));
            } else {
                await new Promise(r => requestAnimationFrame(r));
            }
        }

        // Final render to ensure complete
        messageDiv.innerHTML = DOMPurify.sanitize(marked.parse(text));
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

    // Reset input field
    resetInput() {
        const { promptInput, sendBtn } = this.elements;
        promptInput.value = '';
        sendBtn.disabled = true;
        this.autoResize(promptInput);
    },

    // Auto-resize textarea
    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
        this.elements.sendBtn.disabled = !textarea.value.trim();
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
            akashProvider, akashIndicator, icpIndicator, filecoinIndicator,
            modelName, modelBadge,
            providerInfo, modelInfo // Legacy fallback
        } = this.elements;

        if (!statusDot || !statusText) {
            console.warn('Status elements not found');
            return;
        }

        if (connected && healthData) {
            statusDot.classList.remove('disconnected');
            statusDot.classList.add('connected');
            statusText.textContent = 'Connected';
            
            // Extract info from health data
            const gpuType = healthData.gpu_type || 'GPU';
            const model = healthData.model || 'Unknown';
            
            // Update Akash provider display - show GPU type, not deployment name
            if (akashProvider) {
                akashProvider.textContent = `provider.akashprovid.com (${gpuType})`;
            }
            
            // Update status indicators
            if (icpIndicator) icpIndicator.textContent = '●';
            if (akashIndicator) akashIndicator.textContent = '●';
            if (filecoinIndicator) filecoinIndicator.textContent = '●';
            
            // Update model name
            if (modelName) {
                modelName.textContent = model;
            }
            
            // Set up click handlers for all infrastructure modals
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
            
            // ICP modal handler
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
            
            // Filecoin modal handler
            const filecoinStatus = document.getElementById('filecoinStatus');
            if (filecoinStatus && !filecoinStatus._handlerAttached) {
                filecoinStatus._handlerAttached = true;
                filecoinStatus.onclick = (e) => {
                    e.preventDefault();
                    import('./modals.js').then(({ default: Modals }) => {
                        Modals.showFilecoinStorageModal();
                    });
                };
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
            if (filecoinIndicator) filecoinIndicator.textContent = '○';
            
            if (modelName) modelName.textContent = 'Offline';
            if (akashProvider) akashProvider.textContent = errorDetail || 'Connection failed';
            
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

export default Messages;
