// ============================================================================
// TRINITY FRONTEND - Refactored Architecture
// ============================================================================
// OVERVIEW:
// Trinity AI is a decentralized AI chat app with ICP auth, Akash compute, and
// Filecoin storage. This is the main frontend application.
//
// ARCHITECTURE:
//   1. CONFIG     - API URLs, environment detection, constants
//   2. Auth       - Ed25519 keypairs (Principal ID = user identity + FIL address)
//   3. Autosave   - Debounced saves to Akash disk (/chats/{principal}/{chatId}.json)
//   4. Archive    - Metadata flags for read-only chats (10 limit, Phase 2: Pinata sync)
//   5. State      - Global app state (chat history, context memory, user memory)
//   6. API        - Signed requests to Flask backend (signature verification)
//   7. UI         - DOM rendering (messages, sidebar, modals, animations)
//   8. Actions    - Business logic (generate, load chats, memory management)
//
// MEMORY SYSTEM (3 LAYERS):
//   1. contextMemory: Last 6 messages sent to LLM (rebuilt when loading old chats)
//   2. conversationSummary: Compressed older messages (every 15 messages)
//   3. userMemory: Persistent facts across ALL chats (user_memory.json per principal)
//
// DATA FLOW:
//   User input → addMessage() → autosave → API.generate() → backend loads userMemory
//   → LLM receives: [user facts] + [summary] + [last 6 msgs] + [new prompt]
//   → AI response → addMessage() → autosave → repeat
//
// STORAGE:
//   - Active chats: Akash disk (/chats/{principal}/{chatId}.json)
//   - User memory: Akash disk (/chats/{principal}/user_memory.json)
//   - Archived chats: Phase 1 = metadata flag, Phase 2 = Pinata bundle
// ============================================================================

// ============================================================================
// IMPORTS
// ============================================================================
import CONFIG from './config.js';
import MockStorage from './storage/mock.js';
import Archive from './modules/archive.js';
import UI from './ui/index.js';
import AuthManager from './auth/authManager.js';
import AutosaveManager from './storage/autosave.js';
import State from './state/store.js';
import ContextMemory from './state/contextMemory.js';
import initRainbowBorders from './ui/rainbowBorder.js';
import { generateViaCanister, healthCheckViaCanister, isCanisterConfigured } from './api/canister-client.js';

// ============================================================================
// 1b. AUTHENTICATION - Imported from auth/authManager.js
// ============================================================================
// Auth module has been extracted to auth/authManager.js
// Provides Ed25519 keypair management, signature generation, and localStorage persistence
// Methods: initialize(), login(), logout(), importKey(), exportKey(), signMessage(), getPublicKeyHex()
// ============================================================================
// 1b. AUTHENTICATION - Imported from auth/authManager.js
// ============================================================================
// Auth module has been extracted to auth/authManager.js
// Provides Ed25519 keypair management, signature generation, and localStorage persistence
// Methods: initialize(), login(), logout(), importKey(), exportKey(), signMessage(), getPublicKeyHex()

// ============================================================================
// 1c. AUTOSAVE MODULE - Imported from storage/autosave.js
// ============================================================================
// Autosave module has been extracted to storage/autosave.js
// Provides debounced chat persistence with retry logic
// Methods: scheduleAutosave(), executeAutosave(), handleAutosaveError(), generateChatTitle()
// Uses callback injection (onSaveSuccess) to avoid circular dependency with Actions.loadChats()
// ============================================================================

// ============================================================================
// 2. STATE MANAGEMENT - Imported from state/store.js
// ============================================================================
// State module has been extracted to state/store.js (Zustand)
// Provides centralized state management with reactive updates
// Modules: state/store.js (main store), state/contextMemory.js (compression)
//
// MEMORY ARCHITECTURE (from original State):
// - chatHistory: Full conversation (persisted to Akash disk via autosave)
// - contextMemory: Last 6 messages sent to LLM (rebuilt when loading old chats)
// - conversationSummary: Compressed older messages (created every 15 messages)
// - userMemory: Persistent facts across ALL chats (synced to user_memory.json)
//
// DATA FLOW:
// User types → State.addMessage() → updates chatHistory & contextMemory
// → autosave to Akash → generate() sends contextMemory + userMemory to LLM
// → AI response → State.addMessage() → cycle repeats
// ============================================================================

// ============================================================================
// 3. API LAYER (ENHANCED)
// ============================================================================
// BACKEND COMMUNICATION:
// - All requests go through request() which adds Ed25519 auth headers
// - Headers: X-Principal, X-Signature, X-Timestamp (verified by @require_auth)
// - Endpoints: /generate, /chat/*, /user/memory
// 
// CONTEXT SENT TO LLM:
// - principal: For user memory lookup
// - contextMemory: Last 6 messages (includes conversation summaries)
// - Backend loads user_memory.json and includes facts in prompt
const API = {
    async request(endpoint, options = {}) {
        const url = `${CONFIG.API_URL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...options.headers
        };

        // Add ICP authentication headers if authenticated
        if (State.isAuthenticated && AuthManager.isInitialized) {
            try {
                const timestamp = Date.now().toString();
                const message = `${State.principal}:${timestamp}:${endpoint}`;
                const signature = await AuthManager.signMessage(message);
                const publicKey = AuthManager.getPublicKeyHex();
                
                if (signature && publicKey) {
                    headers['ICP-Principal'] = State.principal;
                    headers['ICP-Signature'] = signature;
                    headers['ICP-Timestamp'] = timestamp;
                    headers['ICP-PublicKey'] = publicKey;  // For Phase 2 verification
                    
                    console.log('🔐 Request signed:', {
                        principal: State.principal.substring(0, 20) + '...',
                        endpoint,
                        timestamp,
                        signaturePreview: signature.substring(0, 16) + '...',
                        publicKeyPreview: publicKey.substring(0, 16) + '...'
                    });
                }
            } catch (error) {
                console.warn('❌ Failed to sign request:', error);
            }
        }

        try {
            const response = await fetch(url, {
                mode: 'cors',
                headers,
                ...options
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`);
            }

            return response.json();
        } catch (error) {
            console.error(`❌ Request failed to ${url}:`, error);
            throw error;
        }
    },

    async healthCheck() {
        return this.request('/health', { method: 'GET' });
    },

    async generate(prompt, temperature = 0.7, skipContext = false) {
        // =====================================================================
        // ROUTING: ICP Canister (decentralized) vs Direct (legacy Cloudflare)
        // =====================================================================
        // Phase 3 Complete: Default to ICP canister for full decentralization
        // The canister makes HTTPS outcalls to Akash backend
        // =====================================================================
        
        // Build context messages for LLM
        let contextMessages = [];
        if (!skipContext && State.contextMemory.length > 0) {
            const contextData = State.getContextForLLM();
            contextMessages = contextData.recentMessages;
            console.log(`✅ CONTEXT ENABLED: Sending ${contextMessages.length} context messages to LLM`);
            console.log(`📊 Context includes summary: ${contextData.compressionRatio !== 'none'}`);
            console.log(`🔍 Context preview:`, contextMessages.map(m => `${m.role}: ${m.content.substring(0, 50)}...`));
            if (State.userMemory && State.userMemory.facts && State.userMemory.facts.length > 0) {
                console.log(`🧠 Including ${State.userMemory.facts.length} user memory facts`);
            }
        } else {
            console.warn(`⚠️ CONTEXT DISABLED: skipContext=${skipContext}, contextMemory.length=${State.contextMemory.length}`);
        }
        
        // Route through ICP canister (fully decentralized)
        if (CONFIG.USE_CANISTER && isCanisterConfigured()) {
            console.log('📡 Routing through ICP canister (decentralized path)');
            try {
                const result = await generateViaCanister(prompt, contextMessages);
                // Transform canister response to match legacy format
                return {
                    generated_text: result.response,
                    model: result.model,
                    provider_id: result.provider_id,
                    done: result.done
                };
            } catch (error) {
                console.error('❌ Canister path failed:', error);
                throw error;
            }
        }
        
        // Fallback: Direct HTTP path (legacy Cloudflare route)
        console.log('☁️ Using direct HTTP path (legacy)');
        const body = {
            prompt,
            max_length: -1,
            temperature,
            principal: State.principal
        };
        
        if (contextMessages.length > 0) {
            body.contextMemory = contextMessages;
        }

        return this.request('/generate', {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },

    // NEW ENDPOINTS FOR AUTOSAVE, ARCHIVE, ETC
    async autosave(chatData) {
        const payload = {
            chatId: State.currentChatId,
            messages: State.chatHistory,
            metadata: {
                title: chatData?.title || State.chatHistory[0]?.content?.substring(0, 50) || 'Untitled Chat',
                updatedAt: Date.now()
            }
        };
        
        console.log('📤 Autosave API call:', {
            endpoint: '/chat/autosave',
            chatId: payload.chatId,
            messageCount: payload.messages.length,
            title: payload.metadata.title
        });
        
        try {
            const response = await this.request('/chat/autosave', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            console.log('📥 Autosave API response:', response);
            return response;
        } catch (error) {
            console.error('📥 Autosave API error:', {
                message: error.message,
                endpoint: '/chat/autosave',
                payload
            });
            throw error;
        }
    },

    async listChats() {
        return this.request('/chat/list', { method: 'GET' });
    },

    async loadChat(chatId) {
        return this.request(`/chat/${chatId}`, { method: 'GET' });
    },

    async deleteChat(chatId) {
        return this.request(`/chat/${chatId}`, { method: 'DELETE' });
    },

    async archiveChat(chatId) {
        return this.request(`/chat/${chatId}/archive`, { method: 'POST' });
    },

    // Archive recovery endpoints (Filecoin/IPFS)
    async recoverArchives() {
        return this.request('/chat/recover-archives', { method: 'GET' });
    },

    async getArchivedChat(cid) {
        return this.request(`/chat/archive/${cid}`, { method: 'GET' });
    },

    // User memory endpoints
    async getUserMemory() {
        return this.request('/user/memory', { method: 'GET' });
    },
    
    async updateUserMemory(memory) {
        return this.request('/user/memory', {
            method: 'POST',
            body: JSON.stringify(memory)
        });
    },
    
    async addMemoryFact(fact, chatId = null, category = 'general') {
        return this.request('/user/memory/fact', {
            method: 'POST',
            body: JSON.stringify({ fact, chatId, category })
        });
    },
    
    async deleteMemoryFact(index) {
        return this.request(`/user/memory/fact/${index}`, { method: 'DELETE' });
    }
};

// NOTE: recoverArchivedChat() removed - no longer needed
// Archives are just metadata flags, all chats accessible via /chats endpoint

// ============================================================================
// 4. UI (View Layer) - Imported from ui/index.js
// ============================================================================
// UI module has been split into 5 sub-modules:
// - ui/domCache.js: DOM element caching and initialization
// - ui/messages.js: Message rendering, typing animations, connection status
// - ui/sidebar.js: Sidebar rendering with chat list and auth buttons
// - ui/modals.js: Modal dialogs and input prompts
// - ui/notifications.js: Toast notifications and autosave indicators
// 
// The UI module is imported at the top of this file.

// ============================================================================
// 5. ACTIONS (Business Logic)
// ============================================================================
// USER ACTIONS:
// - generate(): Main chat flow (add user message → call LLM → display response)
// - loadChat(): Load old chat + rebuild contextMemory from last 6 messages
// - archiveChat(): Set isArchived=true, enforce 10 limit, auto-start new chat if current
// - viewMemory(): Show user memory modal (persistent facts across all chats)
// - login/logout: Ed25519 keypair management
// 
// MEMORY LOADING:
// - loadChats(): Get all chats from backend (active + archived)
// - loadUserMemory(): Get persistent facts from user_memory.json
const Actions = {
    // Check backend connection
    async checkConnection() {
        try {
            let data;
            
            // Route health check through ICP canister when enabled
            if (CONFIG.USE_CANISTER && isCanisterConfigured()) {
                console.log('🏥 Checking health via ICP canister...');
                data = await healthCheckViaCanister();
                console.log('Health check response (via canister):', data);
            } else {
                console.log('Checking connection to:', `${CONFIG.API_URL}/health`);
                data = await API.healthCheck();
                console.log('Health check response:', data);
            }

            if (data.status === 'healthy' || data.ollama_connected) {
                UI.updateConnectionStatus(true, data.provider_id, data.model);
                console.log('✅ Successfully connected to Akash backend');
            } else {
                console.warn('Backend returned unhealthy status:', data);
                UI.updateConnectionStatus(false, null, null, 'Backend unhealthy');
            }
        } catch (error) {
            console.error('Connection error:', error);
            let detail = error.message;

            if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                detail = 'Network error - check if Akash deployment is running';
            } else if (error.message.includes('CORS')) {
                detail = 'CORS error - backend may need CORS headers';
            } else if (error.message.includes('canister')) {
                detail = 'ICP canister error - check canister deployment';
            }

            UI.updateConnectionStatus(false, null, null, detail);
        }
    },

    // Send message and get AI response
    async generate() {
        // SECURITY: Block if not authenticated
        if (!State.isAuthenticated) {
            console.warn('⛔ Generate blocked - user not authenticated');
            UI.showNotification('⛔ Please log in to use Trinity', 'error');
            return;
        }
        
        // Prevent double-submit
        if (State.isGenerating) return;

        const prompt = UI.elements.promptInput.value.trim();
        if (!prompt) return;

        // Initialize new chat if needed
        if (!State.chatStarted) {
            UI.showChatArea();
            State.setChatStarted(true);
            State.setCurrentChatId(State.generateChatId());
        }

        UI.setGenerating(true, State);

        // Add user message
        State.addMessage('user', prompt);
        UI.showMessage('user', prompt);
        UI.resetInput();

        // Debug: Log current context
        console.log('📝 Current context memory:', State.contextMemory.length, 'messages');
        console.log('📝 Context:', State.contextMemory.map(m => `${m.role}: ${m.content.substring(0, 50)}...`));

        // Show loading indicator
        const loadingId = UI.showMessage('ai', '<div class="loading-dots"><span></span><span></span><span></span></div>');

        try {
            let generatedText;

            console.log('🔍 TEST_MODE:', CONFIG.TEST_MODE, 'API_URL:', CONFIG.API_URL);

            if (CONFIG.TEST_MODE) {
                // Test mode - use mock responses
                console.warn('⚠️ Using TEST_MODE - mock responses');
                await new Promise(r => setTimeout(r, 1000));
                generatedText = CONFIG.TEST_RESPONSES[State.testResponseIndex % CONFIG.TEST_RESPONSES.length];
                State.incrementTestResponseIndex();
            } else {
                // Production - call API
                console.log('📤 Sending request to:', `${CONFIG.API_URL}/generate`);
                const data = await API.generate(prompt);
                console.log('📥 Response data:', data);

                generatedText = data.generated_text;
                console.log('✅ Generated text length:', generatedText ? generatedText.length : 0);

                if (data.error) {
                    throw new Error(data.error);
                }
            }

            UI.removeMessage(loadingId);
            UI.setLoading(false, State); // Ensure loading state is cleared

            if (generatedText) {
                console.log('💬 Displaying message...');
                State.addMessage('assistant', generatedText);

                // Create message div and append it, then animate
                const { messagesContainer } = UI.elements;
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ai';
                messageDiv.id = 'msg-' + Date.now();
                messagesContainer.appendChild(messageDiv);

                // Animate the typing
                await UI.typeMessage(messageDiv, generatedText);

                // Check if summarization is needed (after successful response)
                if (State.chatHistory.length >= State.SUMMARY_INTERVAL && 
                    State.chatHistory.length - State.lastSummaryAt >= State.SUMMARY_INTERVAL) {
                    console.log(`📊 Conversation has ${State.chatHistory.length} messages, triggering summarization...`);
                    // Run in background - don't block UI
                    ContextMemory.compressContext().catch(err => 
                        console.error('Failed to compress context:', err)
                    );
                }

                // Trigger autosave if authenticated
                if (State.isAuthenticated) {
                    console.log('💾 Triggering autosave after message exchange...');
                    AutosaveManager.scheduleAutosave(
                        {
                            messages: State.chatHistory,
                            title: State.chatHistory[0]?.content?.substring(0, 50) || 'Untitled Chat'
                        },
                        State.currentChatId,
                        State.isAuthenticated,
                        UI.showAutosaveIndicator,
                        () => this.executeAutosave()
                    );
                }
            } else {
                console.error('❌ No generated text received');
                UI.showMessage('ai', '❌ No response generated');
            }
        } catch (error) {
            console.error('❌ Generate error:', error);
            UI.removeMessage(loadingId);
            UI.showMessage('ai', `❌ Request failed: ${error.message}`);
        } finally {
            UI.setGenerating(false, State);
        }
    },

    // Start a new chat
    newChat() {
        // SECURITY: Block if not authenticated
        if (!State.isAuthenticated) {
            console.warn('⛔ New chat blocked - user not authenticated');
            return;
        }
        
        UI.clearMessages();
        UI.resetInput();
        State.reset();
        UI.renderSidebar(State);
    },

    // Toggle sidebar visibility
    toggleSidebar() {
        UI.elements.sidebar.classList.toggle('collapsed');

        // On mobile, set up click-outside-to-close
        if (window.innerWidth <= 768 && !UI.elements.sidebar.classList.contains('collapsed')) {
            document.addEventListener('click', this.closeSidebarOnClickOutside);
        } else {
            document.removeEventListener('click', this.closeSidebarOnClickOutside);
        }
    },

    // Close sidebar when clicking outside (mobile)
    closeSidebarOnClickOutside(event) {
        const sidebar = UI.elements.sidebar;
        const toggleBtn = UI.elements.toggleSidebarBtn;

        if (!sidebar.contains(event.target) && !toggleBtn.contains(event.target)) {
            sidebar.classList.add('collapsed');
            document.removeEventListener('click', Actions.closeSidebarOnClickOutside);
        }
    },

    // Handle Enter key in input
    handleKeyDown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (event.target.value.trim()) {
                this.generate();
            }
        }
    },

    // ============ NEW ACTIONS ============

    // Initialize authentication (mandatory gate)
    async initAuth() {
        console.log('🔐 Starting authentication initialization...');
        
        try {
            const result = await AuthManager.initialize();
            
            if (result && result.isAuthenticated) {
                // Restore State from AuthManager result
                State.setAuthenticated(result.principal, result.authenticatedSince);
                console.log('✅ Identity restored from cache:', result.principal);

                // Render authenticated UI immediately
                UI.renderSidebar(State);

                // Load user data in background (non-blocking)
                this.loadUserDataInBackground();
            } else {
                // No cached credentials - enforce authentication
                console.log('🚫 No cached session - authentication required');
                UI.renderSidebar(State);
                
                // Show authentication modal (loops until successful)
                await this.requireAuthentication();
            }
        } catch (err) {
            console.error('❌ Auth initialization error:', err);
            UI.renderSidebar(State);
            
            // Enforce authentication on error
            await this.requireAuthentication();
        }
    },
    
    // Require authentication (loops until successful)
    async requireAuthentication() {
        console.log('🔒 Authentication required - showing modal...');
        
        while (!State.isAuthenticated) {
            try {
                await this.handleAuthenticationFlow();
                
                // If still not authenticated after flow, loop continues
                if (!State.isAuthenticated) {
                    console.log('⚠️ Authentication incomplete, retrying...');
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
            } catch (error) {
                console.error('❌ Authentication flow error:', error);
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        }
        
        console.log('✅ Authentication successful!');
    },
    
    // Handle authentication flow (returns only when authenticated)
    async handleAuthenticationFlow() {
        const { default: Modals } = await import('./ui/modals.js');
        
        // Show authentication choice modal
        const choice = await Modals.showAuthChoiceModal();
        
        if (choice === 'create') {
            // Create new identity flow
            await this.createNewIdentity();
        } else if (choice === 'login') {
            // Login flow
            await this.loginWithCredentials();
        }
        // If cancelled or failed, function returns and requireAuthentication loops
    },
    
    // Create new identity with automatic login after credentials shown
    async createNewIdentity() {
        try {
            const result = await AuthManager.login();
            console.log('🔑 New identity created:', result.principal?.substring(0, 20) + '...');
            
            if (!result.success) {
                console.error('❌ Identity creation failed');
                return; // Return to auth choice modal
            }
            
            // Import Modals dynamically
            const { default: Modals } = await import('./ui/modals.js');
            
            // Show credentials warning (only "Okay" button, no cancel)
            await Modals.showKeyWarningModal(result.principal, result.privateKeyHex);
            
            // User clicked Okay - automatically authenticate them
            State.setAuthenticated(result.principal, result.authenticatedSince);
            
            // Clear all modals
            Modals.removeAllModals();
            
            // Update UI immediately - don't wait for data loading
            UI.renderSidebar(State);
            console.log('✅ New user authenticated!');
            
            // Load user data in background (non-blocking)
            // These may fail if backend is slow/unavailable, but auth is complete
            this.loadUserDataInBackground();

        } catch (error) {
            console.error('❌ Create identity error:', error);
            // Return to auth choice modal on error
        }
    },
    
    // Load user data in background (non-blocking, errors don't break auth)
    async loadUserDataInBackground() {
        console.log('📂 Loading user data in background...');
        
        try {
            await this.loadChats();
        } catch (error) {
            console.warn('⚠️ Failed to load chats (will retry later):', error.message);
        }
        
        try {
            await this.loadUserMemory();
        } catch (error) {
            console.warn('⚠️ Failed to load user memory (will retry later):', error.message);
        }
        
        try {
            await this.recoverArchivedChats();
        } catch (error) {
            console.warn('⚠️ Failed to recover archives (will retry later):', error.message);
        }
        
        // Final UI update after all data loaded
        UI.renderSidebar(State);
        console.log('📂 Background data loading complete');
    },

    // Logout
    async logout() {
        await AuthManager.logout();
        State.clearAuthentication();
        State.reset();
        UI.clearMessages();
        UI.renderSidebar(State);
        
        // Show authentication modal immediately after logout
        await this.requireAuthentication();
    },

    // Login with existing credentials
    async loginWithCredentials() {
        const { default: Modals } = await import('./ui/modals.js');
        
        try {
            // Show login modal with username and password
            const credentials = await Modals.showLoginModal();
            if (!credentials) {
                console.log('🚫 Login cancelled by user');
                return; // Return to auth choice modal
            }

            // Use the password (private key) to restore identity
            const result = await AuthManager.importKey(credentials.password);
            
            if (!result.success) {
                throw new Error(result.error || 'Import failed');
            }
            
            // Verify username matches
            if (result.principal !== credentials.username) {
                throw new Error('Username does not match the provided password');
            }
            
            // Authentication successful
            State.setAuthenticated(result.principal, result.authenticatedSince);
            
            // Clear all modals
            Modals.removeAllModals();
            
            console.log('✅ Identity restored:', result.principal);
            
            // Show success notification
            UI.showNotification('✅ Welcome back!', 'success');

            // Update UI immediately
            UI.renderSidebar(State);

            // Load user data in background (non-blocking)
            this.loadUserDataInBackground();
            
        } catch (error) {
            console.error('❌ Login failed:', error);
            UI.showNotification('❌ Invalid credentials. Please try again.', 'error');
            // Return to auth choice modal on error
        }
    },

    // Export current key
    async exportKey() {
        const result = AuthManager.exportKey();
        
        if (result.success) {
            // Use the same modal as identity creation
            const { default: Modals } = await import('./ui/modals.js');
            await Modals.showKeyWarningModal(result.principal, result.privateKeyHex);
        } else {
            UI.showNotification('❌ No identity to export', 'error');
        }
    },

    // Load all chats for authenticated user
    async loadChats() {
        if (!State.isAuthenticated) {
            console.log('❌ loadChats() skipped - not authenticated');
            return;
        }

        try {
            console.log('📋 Loading chats...');
            
            let chats;
            if (CONFIG.TEST_MODE) {
                // Use mock storage for test mode
                chats = MockStorage.listChats();
            } else {
                // Use real API for production
                const response = await API.listChats();
                chats = response.chats || [];
            }
            
            console.log('📋 Chats loaded:', chats.length);
            State.setAllChats(chats);
            UI.renderSidebar(State);
            console.log('📋 Sidebar rendered with chats');
        } catch (error) {
            console.error('❌ Failed to load chats:', error);
        }
    },
    
    // Execute autosave (wrapper for AutosaveManager)
    async executeAutosave() {
        const result = await AutosaveManager.executeAutosave({
            currentChatId: State.currentChatId,
            chatHistory: State.chatHistory,
            isAuthenticated: State.isAuthenticated,
            testMode: CONFIG.TEST_MODE,
            principal: State.principal,
            apiSave: (chatData) => API.autosave(chatData),
            mockSave: (chatId, data) => MockStorage.saveChat(chatId, data),
            showIndicator: UI.showAutosaveIndicator,
            hideIndicator: UI.hideAutosaveIndicator,
            retryCallback: () => this.executeAutosave()
        });
        
        // Update State based on result
        if (result.success) {
            State.setAutosaveStatus(result.autosaveStatus);
            State.setUnsavedChanges(result.unsavedChanges);
        } else if (result.autosaveStatus) {
            State.setAutosaveStatus(result.autosaveStatus);
        }
        
        return result;
    },

    // Load user memory (persistent facts)
    async loadUserMemory() {
        if (!State.isAuthenticated) {
            console.log('❌ loadUserMemory() skipped - not authenticated');
            return;
        }

        try {
            console.log('🧠 Loading user memory...');
            const memory = await API.getUserMemory();
            State.setUserMemory(memory);
            console.log(`🧠 User memory loaded: ${memory.facts?.length || 0} facts`);
        } catch (error) {
            console.error('❌ Failed to load user memory:', error);
            // Initialize empty memory on error
            State.setUserMemory({ facts: [], preferences: {} });
        }
    },

    // Recover archived chats from Filecoin (auto-called on login)
    async recoverArchivedChats() {
        if (!State.isAuthenticated) {
            console.log('❌ recoverArchivedChats() skipped - not authenticated');
            return;
        }

        try {
            console.log('📦 Recovering archived chats from Filecoin...');
            const response = await API.recoverArchives();

            if (!response.success) {
                console.log('ℹ️ No archives to recover:', response.message);
                return;
            }

            const archives = response.archives || [];
            console.log(`📦 Found ${archives.length} archived chats in Filecoin`);

            if (archives.length === 0) {
                return;
            }

            // Merge recovered archives into local state
            // Only add archives that aren't already in allChats
            const existingChatIds = new Set(State.allChats.map(c => c.chatId));
            let newCount = 0;

            for (const archive of archives) {
                if (!existingChatIds.has(archive.chatId)) {
                    // Add recovered archive to state
                    State.allChats.push({
                        chatId: archive.chatId,
                        title: archive.title || 'Recovered Chat',
                        isArchived: true,
                        archivedAt: archive.archivedAt,
                        filecoinCID: archive.cid,
                        messageCount: archive.messageCount || 0,
                        recoveredFromFilecoin: true
                    });
                    newCount++;
                }
            }

            if (newCount > 0) {
                console.log(`✅ Recovered ${newCount} new archived chats from Filecoin`);
                UI.renderSidebar(State);
                UI.showNotification(`📦 Recovered ${newCount} archived chat(s) from Filecoin`, 'success');
            } else {
                console.log('ℹ️ All archived chats already synced locally');
            }

        } catch (error) {
            console.error('❌ Failed to recover archives:', error);
            // Don't show error to user - this is a background operation
            // They can still use the app, just without recovered archives
        }
    },

    // Load specific chat
    async loadChat(chatId) {
        // SECURITY: Block if not authenticated
        if (!State.isAuthenticated) {
            console.warn('⛔ Load chat blocked - user not authenticated');
            return;
        }
        
        try {
            let chatData;
            if (CONFIG.TEST_MODE) {
                chatData = MockStorage.loadChat(chatId);
                if (!chatData) throw new Error('Chat not found');
            } else {
                const response = await API.loadChat(chatId);
                chatData = response;
            }
            
            State.setChatHistory(chatData.messages || []);
            State.setCurrentChatId(chatData.chatId || chatId);
            State.setChatStarted(true);
            
            // Rebuild context memory from last 6 messages
            State.setContextMemory([]);
            const recentMessages = State.chatHistory.slice(-State.CONTEXT_WINDOW_SIZE);
            recentMessages.forEach(msg => State.updateContextMemory(msg));
            console.log(`🔄 Loaded chat with ${State.chatHistory.length} messages, rebuilt context with ${State.contextMemory.length} recent messages`);
            
            UI.renderChatHistory(State);
            
            // Check if this is an archived chat and disable input
            const currentChat = State.allChats.find(c => c.chatId === chatId);
            if (currentChat && currentChat.isArchived) {
                if (UI.elements.promptInput) UI.elements.promptInput.disabled = true;
                if (UI.elements.submitButton) UI.elements.submitButton.disabled = true;
                UI.showWarning('📦 Archived chat (read-only). Cannot send new messages. Start a new chat to continue.');
            } else {
                // Re-enable input for non-archived chats
                if (UI.elements.promptInput) UI.elements.promptInput.disabled = false;
                if (UI.elements.submitButton) UI.elements.submitButton.disabled = false;
            }
        } catch (error) {
            UI.showError('Failed to load chat: ' + error.message);
        }
    },

    // Delete chat
    async deleteChat(chatId) {
        const confirmed = await UI.showConfirmDialog(
            'Delete chat?',
            'This action cannot be undone.'
        );

        if (!confirmed) return;

        try {
            if (CONFIG.TEST_MODE) {
                MockStorage.deleteChat(chatId);
            } else {
                await API.deleteChat(chatId);
            }
            
            State.setAllChats(State.allChats.filter(c => c.chatId !== chatId));
            if (State.currentChatId === chatId) {
                this.newChat();
            }
            UI.renderSidebar(State);
            UI.showSuccess('Chat deleted');
        } catch (error) {
            UI.showError('Failed to delete chat: ' + error.message);
        }
    },
    
    // View and manage user memory
    async viewMemory() {
        if (!State.userMemory) {
            UI.showError('User memory not loaded');
            return;
        }

        const facts = State.userMemory.facts || [];
        
        const dialog = document.createElement('div');
        dialog.className = 'modal-dialog';
        dialog.innerHTML = `
            <div class="modal-content" style="max-width: 600px; max-height: 80vh;">
                <h3 style="margin-bottom: 12px;">🧠 Your Memory</h3>
                <p style="font-size: 13px; color: #aaa; margin-bottom: 16px;">
                    These facts persist across all your chats. The AI remembers them automatically.
                </p>
                
                <div style="margin-bottom: 16px;">
                    <input type="text" id="newFactInput" placeholder="Add a new fact..." 
                        style="width: 100%; padding: 10px; background: #2a2a2a; border: 1px solid #444; border-radius: 4px; color: white; font-size: 14px; margin-bottom: 8px;">
                    <button data-action="addNewFact" style="background: #9C27B0; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 13px;">
                        ➕ Add Fact
                    </button>
                </div>
                
                <div id="factsList" style="max-height: 300px; overflow-y: auto; margin-bottom: 16px;">
                    ${facts.length === 0 ? 
                        '<p style="text-align: center; color: #666; padding: 20px;">No facts yet. Add one above!</p>' :
                        facts.map((fact, index) => `
                            <div style="background: #2a2a2a; padding: 12px; border-radius: 4px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: start;">
                                <div style="flex: 1;">
                                    <div style="color: white; margin-bottom: 4px;">${fact.fact}</div>
                                    <div style="font-size: 11px; color: #666;">
                                        ${new Date(fact.addedAt).toLocaleDateString()} 
                                        ${fact.category ? `• ${fact.category}` : ''}
                                    </div>
                                </div>
                                <button data-action="deleteFact" data-fact-index="${index}" style="background: #f44336; color: white; padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; margin-left: 8px;">
                                    🗑️
                                </button>
                            </div>
                        `).join('')
                    }
                </div>
                
                <button data-action="closeMemoryDialog" style="background: #555; color: white; padding: 10px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 14px;">
                    Close
                </button>
            </div>
        `;
        document.body.appendChild(dialog);
    },

    // Add a new memory fact
    async addMemoryFact(fact) {
        if (!fact || !fact.trim()) return;

        try {
            const response = await API.addMemoryFact(fact, State.currentChatId);
            // Immutable update - create new object with updated facts
            const currentMemory = State.userMemory || { facts: [], preferences: {} };
            State.setUserMemory({
                ...currentMemory,
                facts: [...currentMemory.facts, response.fact]
            });

            // Close and reopen dialog with updated data
            const dialog = document.querySelector('.modal-dialog');
            if (dialog) dialog.remove();
            await Actions.viewMemory();

            UI.showSuccess('Fact added to memory');
        } catch (error) {
            UI.showError('Failed to add fact: ' + error.message);
        }
    },

    // Delete a memory fact
    async deleteMemoryFact(index) {
        try {
            await API.deleteMemoryFact(index);
            // Immutable update - create new object with filtered facts
            const currentMemory = State.userMemory || { facts: [], preferences: {} };
            State.setUserMemory({
                ...currentMemory,
                facts: currentMemory.facts.filter((_, i) => i !== index)
            });

            // Close and reopen dialog with updated data
            const dialog = document.querySelector('.modal-dialog');
            if (dialog) dialog.remove();
            await Actions.viewMemory();

            UI.showSuccess('Fact removed');
        } catch (error) {
            UI.showError('Failed to delete fact: ' + error.message);
        }
    },

    // Archive current chat
    async archiveCurrentChat() {
        if (!State.currentChatId) {
            UI.showError('No chat to archive');
            return;
        }
        
        if (CONFIG.TEST_MODE) {
            // Mock archive in test mode
            const response = MockStorage.archiveChat(State.currentChatId);
            if (response.success) {
                Archive.showRecoveryIdDialog(response.filepointId);
                State.setAllChats(State.allChats.filter(c => c.chatId !== State.currentChatId));
                State.setCurrentChatId(null);
                UI.resetToNewChat();
                UI.renderSidebar(State);
            }
            return;
        }
        
        // Real archive implementation would go here
        UI.showError('Archive feature coming soon');
    }
};

// ============================================================================
// ENVIRONMENT DETECTION
// ============================================================================
async function detectEnvironment() {
    console.log('🔍 Detecting environment...');
    
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;
    
    // Development mode: file://, localhost, or 127.0.0.1
    const isDevelopment = protocol === 'file:' || 
                         hostname === 'localhost' || 
                         hostname === '127.0.0.1' ||
                         hostname === '';
    
    const isProductionDomain = hostname === 'trinityai.cc' || 
                               hostname === 'www.trinityai.cc' ||
                               hostname.includes('icp0.io') ||
                               hostname.includes('ic0.app');
    
    console.log('📍 Location:', { hostname, protocol, isDevelopment, isProductionDomain });
    
    const preferredEnv = CONFIG.getPreferredEnvironment();
    let localAvailable = false;
    
    // ONLY check for localhost backend in development mode
    if (isDevelopment) {
        console.log('🔧 Development mode - checking for local backend');
        try {
            const testResponse = await fetch('http://localhost:8000/health', {
                method: 'GET',
                mode: 'cors',
                cache: 'no-cache',
                signal: AbortSignal.timeout(2000)
            });
            
            if (testResponse.ok) {
                const health = await testResponse.json();
                localAvailable = true;
                CONFIG._availableEnvironments.local = 'http://localhost:8000';
                console.log('✅ Local backend available:', health.model);
            }
        } catch (err) {
            console.log('ℹ️ Local backend not available:', err.message);
        }
    } else {
        console.log('🌐 Production domain - local backend disabled');
    }
    
    // Set production URL (always available as fallback)
    const prodURL = CONFIG.API_URL;
    CONFIG._availableEnvironments.production = prodURL;
    console.log('✅ Production backend:', prodURL);
    
    // Determine which environment to use
    if (isProductionDomain) {
        // Force production on public domains
        console.log('🔒 Production domain - using Akash backend');
        CONFIG.setAPIURL(prodURL, false);
    } else if (preferredEnv === 'local' && localAvailable) {
        // User preference: local (and it's available)
        console.log('🔧 Using preferred LOCAL environment');
        console.log('⚙️ Setting TEST_MODE to FALSE');
        CONFIG.setAPIURL('http://localhost:8000', false);
    } else if (preferredEnv === 'production') {
        // User preference: production
        console.log('🔧 Using preferred PRODUCTION environment');
        CONFIG.setAPIURL(prodURL, false);
    } else if (localAvailable) {
        // Default to local in development if available
        console.log('🔧 Defaulting to LOCAL environment');
        console.log('⚙️ Setting TEST_MODE to FALSE');
        CONFIG.setAPIURL('http://localhost:8000', false);
    } else {
        // Fallback to production
        console.log('🔧 Using PRODUCTION environment');
        CONFIG.setAPIURL(prodURL, false);
    }
    
    console.log('🎯 Final API URL:', CONFIG.API_URL);
}

// ============================================================================
// INITIALIZATION
// ============================================================================
async function init() {
    console.log('🚀 Trinity initializing...');
    
    // Check version and clear cache if needed (FIRST - before anything else)
    const versionOK = CONFIG.checkVersion();
    if (!versionOK) {
        console.log('🔄 Version update detected, reloading...');
        return; // Stop initialization, reload will happen
    }
    
    // Initialize UI element cache
    UI.init();
    console.log('✅ UI initialized');

    // Detect environment (test vs production)
    try {
        await detectEnvironment();
        console.log('✅ Environment detected:', CONFIG.API_URL);
    } catch (error) {
        console.error('❌ Environment detection failed:', error);
        // Fallback to production if detection fails
        CONFIG.setAPIURL(CONFIG.API_URL, false);
    }

    // Show environment switcher in development mode (even if only one backend available)
    const isDevelopment = window.location.protocol === 'file:' ||
                          window.location.hostname === 'localhost' || 
                          window.location.hostname === '127.0.0.1' ||
                          window.location.hostname === '';
    
    console.log('🔍 Switcher check:', { 
        isDevelopment, 
        hasLocal: !!CONFIG._availableEnvironments.local, 
        hasProduction: !!CONFIG._availableEnvironments.production 
    });
    
    // Show switcher in development mode if we have production backend (local is optional)
    if (isDevelopment && CONFIG._availableEnvironments.production) {
        console.log('🔀 Showing environment switcher');
        UI.showEnvironmentSwitcher(Actions);
    } else {
        console.log('ℹ️ Switcher hidden - production mode or no backends available');
    }

    // Render sidebar immediately (don't wait for auth)
    UI.renderSidebar(State);
    console.log('✅ Sidebar rendered');

    // Set up Autosave callback to break circular dependency
    AutosaveManager.onSaveSuccess = () => Actions.loadChats();

    // Disable UI interactions until authenticated
    UI.disableUI();
    console.log('🚫 UI disabled - waiting for authentication');

    // Initialize authentication (BLOCKS until authenticated)
    await Actions.initAuth();
    
    // Enable UI after authentication
    UI.enableUI();
    console.log('✅ UI enabled - user authenticated');

    // Configure marked.js for markdown rendering
    marked.setOptions({
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(code, { language: lang }).value;
                } catch (err) {}
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true,
        gfm: true
    });

    // -------------------- Event Listeners --------------------

    // Send button
    UI.elements.sendBtn.addEventListener('click', () => Actions.generate());

    // Input field
    UI.elements.promptInput.addEventListener('keydown', (e) => Actions.handleKeyDown(e));
    UI.elements.promptInput.addEventListener('input', (e) => UI.autoResize(e.target));
    UI.elements.promptInput.addEventListener('focus', () => {
        setTimeout(() => UI.handleKeyboardChange(State), 300);
    });
    UI.elements.promptInput.addEventListener('blur', () => {
        setTimeout(() => UI.handleKeyboardChange(State), 300);
    });

    // Sidebar toggles
    if (UI.elements.toggleSidebarBtn) {
        UI.elements.toggleSidebarBtn.addEventListener('click', () => Actions.toggleSidebar());
    }
    if (UI.elements.sidebarToggleBtn) {
        UI.elements.sidebarToggleBtn.addEventListener('click', () => Actions.toggleSidebar());
    }

    // Window resize - collapse sidebar on mobile
    window.addEventListener('resize', () => {
        if (window.innerWidth <= 768) {
            UI.elements.sidebar.classList.add('collapsed');
        }
    });

    // -------------------- Event Delegation for Data Attributes --------------------
    // Handle all data-action clicks via event delegation
    document.addEventListener('click', (e) => {
        // Ignore clicks inside modals (z-index >= 10000)
        const clickedElement = e.target;
        let parent = clickedElement;
        while (parent) {
            const zIndex = window.getComputedStyle(parent).zIndex;
            if (zIndex && parseInt(zIndex) >= 10000) {
                return; // Click is inside a modal, ignore it
            }
            parent = parent.parentElement;
        }
        
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        
        const action = btn.dataset.action;
        const chatId = btn.dataset.chatId;
        const factIndex = btn.dataset.factIndex;
        
        // Prevent event bubbling for nested elements
        e.stopPropagation();
        
        // Route actions
        if (action === 'loadChat' && chatId) Actions.loadChat(chatId);
        else if (action === 'archiveChat' && chatId) Archive.initiateArchive(chatId);
        else if (action === 'newChat') Actions.newChat();
        else if (action === 'login') Actions.login();
        else if (action === 'logout') Actions.logout();
        else if (action === 'importKey') Actions.importKey();
        else if (action === 'exportKey') Actions.exportKey();
        else if (action === 'viewMemory') Actions.viewMemory();
        else if (action === 'addNewFact') {
            const input = document.getElementById('newFactInput');
            const fact = input?.value?.trim();
            if (fact) {
                Actions.addMemoryFact(fact);
            }
        }
        else if (action === 'deleteFact' && factIndex !== undefined) {
            Actions.deleteMemoryFact(parseInt(factIndex));
        }
        else if (action === 'closeMemoryDialog') {
            const dialog = btn.closest('.modal-dialog');
            if (dialog) dialog.remove();
        }
    });

    // Handle hover effects for chat items
    document.addEventListener('mouseover', (e) => {
        const chatItem = e.target.closest('.chat-item');
        if (!chatItem) return;
        chatItem.style.background = '#3d3d3d';
        const archiveBtn = chatItem.querySelector('.archive-btn');
        if (archiveBtn) archiveBtn.style.display = 'inline-block';
    });

    document.addEventListener('mouseout', (e) => {
        const chatItem = e.target.closest('.chat-item');
        if (!chatItem) return;
        chatItem.style.background = '#2d2d2d';
        const archiveBtn = chatItem.querySelector('.archive-btn');
        if (archiveBtn) archiveBtn.style.display = 'none';
    });

    // Mobile keyboard handling
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => UI.handleKeyboardChange(State));
        window.visualViewport.addEventListener('scroll', () => UI.handleKeyboardChange(State));
        window.visualViewport.addEventListener('resize', () => UI.scrollToBottom());
    }

    // Initialize rainbow border animations
    initRainbowBorders();
    console.log('✅ Rainbow border animations initialized');

    // -------------------- Initial State --------------------

    // Collapse sidebar on mobile at startup
    if (window.innerWidth <= 768) {
        UI.elements.sidebar.classList.add('no-transition', 'collapsed');
        setTimeout(() => {
            UI.elements.sidebar.classList.remove('no-transition');
        }, 100);
    }

    console.log('✅ Trinity fully initialized');
    
    // Initial connection check - small delay to ensure DOM is ready
    setTimeout(() => {
        console.log('🔍 Starting initial connection check...');
        Actions.checkConnection();
    }, 100);

    // Periodic health check (with cleanup reference)
    const intervalId = setInterval(
        () => Actions.checkConnection(),
        CONFIG.HEALTH_CHECK_INTERVAL_MS
    );
    State.setHealthCheckInterval(intervalId);
}

// Start the app when DOM is ready
document.addEventListener('DOMContentLoaded', init);

// ============================================================================
// GLOBAL EXPORTS (for inline HTML handlers and external module access)
// ============================================================================
// Export modules to window for Archive module to access
window.State = State;
window.API = API;
window.UI = UI;
window.Actions = Actions;

// ES6 exports for use in modules
export { State, API, UI, Actions };

// Legacy function exports (being phased out in favor of data-action attributes)
window.toggleSidebar = () => Actions.toggleSidebar();
window.newChat = () => Actions.newChat();
window.login = () => Actions.login();
window.logout = () => Actions.logout();
window.importKey = () => Actions.importKey();
window.exportKey = () => Actions.exportKey();
window.viewMemory = () => Actions.viewMemory();
window.generate = () => Actions.generate();
window.handleKeyDown = (e) => Actions.handleKeyDown(e);
window.autoResize = (el) => UI.autoResize(el);
window.loadChat = (chatId) => Actions.loadChat(chatId);
window.deleteChat = (chatId) => Actions.deleteChat(chatId);
window.archiveChat = (chatId) => Archive.initiateArchive(chatId);

// Debug helpers (accessible in browser console)
window.debugAuth = () => {
    console.log('=== AUTH DEBUG INFO ===');
    console.log('Auth.isInitialized:', Auth.isInitialized);
    console.log('Auth.authClient:', Auth.authClient);
    console.log('State.isAuthenticated:', State.isAuthenticated);
    console.log('State.principal:', State.principal);
    console.log('window.login function exists:', typeof window.login === 'function');
    console.log('Actions.login function exists:', typeof Actions.login === 'function');
    console.log('======================');
};
window.testLogin = () => {
    console.log('Manual login test...');
    Actions.login();
};
window.testImport = async () => {
    console.log('Testing dynamic import...');
    try {
        const module = await import('https://jspm.dev/@dfinity/auth-client@1.0.1');
        console.log('✅ Import successful!', module);
        return module;
    } catch (error) {
        console.error('❌ Import failed:', error);
        throw error;
    }
};
