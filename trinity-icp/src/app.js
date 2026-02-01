// ============================================================================
// TRINITY FRONTEND - Refactored Architecture
// ============================================================================
// OVERVIEW:
// Trinity AI is a decentralized AI chat app with ICP auth, Akash compute, and
// IPFS storage. This is the main frontend application.
//
// ARCHITECTURE:
//   1. CONFIG     - API URLs, environment detection, constants
//   2. Auth       - Ed25519 keypairs (Principal ID = user identity)
//   3. Autosave   - Debounced saves to IPFS via Lighthouse
//   4. Archive    - Metadata flags for read-only chats (10 limit, Lighthouse/IPFS)
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
//   - Active chats: IPFS via Lighthouse (encrypted)
//   - User memory: IPFS via Lighthouse (encrypted)
//   - Archived chats: Lighthouse SDK → IPFS (permanent)
// ============================================================================

// ============================================================================
// IMPORTS
// ============================================================================
import CONFIG from './config.js';
import UI from './ui/index.js';
import Modals from './ui/modals.js';
import AuthManager from './auth/authManager.js';
import AutosaveManager from './storage/autosave.js';
import State from './state/store.js';
import ContextMemory from './state/contextMemory.js';
import initRainbowBorders from './ui/rainbowBorder.js';
import Validation from './utils/validation.js';
import { protectMath, restoreMath } from './utils/math.js';
import { generateViaCanister, healthCheckViaCanister, isCanisterConfigured } from './api/canister-client.js';
import { initTools, getAttachedContent, clearAttachment } from './tools.js';

/**
 * Parse markdown with math protection
 * Protects LaTeX from being mangled by marked
 */
function parseMarkdownWithMath(content) {
    const { processed, mathBlocks } = protectMath(content);
    let html = marked.parse(processed);
    return restoreMath(html, mathBlocks);
}

// ============================================================================
// 1b. AUTHENTICATION - Imported from auth/authManager.js
// ============================================================================
// Auth module provides Ed25519 keypair management, signature generation, and localStorage persistence
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
// DATA FLOW (Agentic Pipeline):
// User types → State.addMessage('user') → chatHistory updated
// → generate() sends to /generate/agent → backend runs multi-pass pipeline
// → Backend streams: phases (UI only, not saved) + tokens (final answer)
// → AI response complete → State.addMessage('assistant', finalAnswer)
// → autosave triggers → only chatHistory saved to IPFS
//
// WHAT'S SAVED vs EPHEMERAL:
// ✅ SAVED: User prompts, final AI answers (chatHistory → autosave → IPFS)
// ❌ EPHEMERAL: Understanding, planning, critique, search results, phase messages
// This keeps IPFS storage lean - no bloat from internal reasoning chains.
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
    // PERFORMANCE: AbortController for cancelling in-flight requests
    // Prevents resource waste when user navigates away or sends new message
    _currentAbortController: null,

    /**
     * Cancel any ongoing API request (streaming or regular)
     */
    cancelRequest() {
        if (this._currentAbortController) {
            this._currentAbortController.abort();
            this._currentAbortController = null;
            console.log('🛑 Request cancelled');
        }
    },

    async request(endpoint, options = {}) {
        const url = `${CONFIG.API_URL}${endpoint}`;
        
        // Start with session-aware headers (includes X-Trinity-Session if private session active)
        const headers = {
            ...CONFIG.getApiHeaders(),
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

    /**
     * Simple generate - minimal path with no context/auth complexity
     * Just sends prompt → gets response
     */
    async generateSimple(prompt, temperature = 0.7) {
        console.log('🔧 Using SIMPLE generate (no context, no auth)');
        const response = await fetch(`${CONFIG.API_URL}/generate/simple`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: prompt.trim(),
                max_length: 500,
                temperature
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        if (!result.ok) {
            throw new Error(result.error || 'Generate failed');
        }
        
        return { generated_text: result.response, model: result.model };
    },

    async generate(prompt, temperature = 0.7, skipContext = false, documentContext = null) {
        // =====================================================================
        // ROUTING: ICP Canister (decentralized) vs Direct HTTP (local dev)
        // =====================================================================
        // Default: ICP canister for full decentralization
        // Canister makes HTTPS outcalls → Vercel Proxy → Akash backend
        // =====================================================================
        
        // Sanitize prompt input
        const sanitizedPrompt = Validation.sanitizeText(prompt, 50000);
        if (!sanitizedPrompt || sanitizedPrompt.length === 0) {
            throw new Error('Prompt cannot be empty');
        }
        
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
        
        if (documentContext) {
            console.log(`📄 Document attached: ${documentContext.length} chars`);
        }
        
        // Route through ICP canister (fully decentralized)
        if (CONFIG.USE_CANISTER && isCanisterConfigured()) {
            console.log('📡 Routing through ICP canister (decentralized path)');
            try {
                const result = await generateViaCanister(sanitizedPrompt, contextMessages, documentContext);
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
        
        // Fallback: Direct HTTP path (local development or canister bypass)
        console.log('☁️ Using direct HTTP path (local dev)');
        const body = {
            prompt: sanitizedPrompt,
            max_length: 800,  // 800 tokens for detailed responses
            temperature,
            principal: State.principal
        };
        
        if (contextMessages.length > 0) {
            body.contextMemory = contextMessages;
        }
        
        if (documentContext) {
            body.documentContext = documentContext;
        }

        const result = await this.request('/generate', {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        // Transform response to include generated_text (backend returns 'response')
        return {
            generated_text: result.response || result.generated_text,
            model: result.model,
            provider_id: result.provider_id,
            done: result.done
        };
    },

    /**
     * Generate with streaming - tokens appear as they're generated
     * @param {string} prompt - User prompt
     * @param {function} onToken - Callback for each token: (token) => void
     * @param {function} onDone - Callback when complete: (fullText) => void
     * @param {function} onError - Callback on error: (error) => void
     * @param {object} options - Optional settings (temperature, skipContext, documentContext, reasoningMode)
     */
    async generateStream(prompt, onToken, onDone, onError, options = {}) {
        const { temperature = 0.7, skipContext = false, documentContext = null, reasoningMode = false } = options;
        
        // Build context
        let contextMessages = [];
        if (!skipContext && State.contextMemory && State.contextMemory.length > 0) {
            contextMessages = State.contextMemory.slice(-CONFIG.CONTEXT_WINDOW_SIZE * 2);
        }
        
        const body = {
            prompt: prompt.trim(),
            // Deep thinking needs MUCH more tokens: 4000 for /think vs 1000 normal
            max_length: reasoningMode ? 4000 : 1000,
            temperature,
            principal: State.principal,
            contextMemory: contextMessages,
            reasoning_mode: reasoningMode,  // Enable structured reasoning
        };
        
        if (documentContext) {
            body.documentContext = documentContext;
        }
        
        const url = `${CONFIG.API_URL}/generate/stream`;
        console.log('🌊 Starting stream:', url);

        // Cancel any existing request before starting a new one
        this.cancelRequest();
        this._currentAbortController = new AbortController();
        const signal = this._currentAbortController.signal;

        try {
            const response = await fetch(url, {
                method: 'POST',
                mode: 'cors',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body),
                signal, // PERFORMANCE: Allow request cancellation
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) {
                    console.log('🌊 Stream complete:', fullText.length, 'chars');
                    onDone(fullText);
                    break;
                }
                
                // Decode chunk and add to buffer
                buffer += decoder.decode(value, { stream: true });
                
                // Process complete SSE messages from buffer
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            if (data.token) {
                                fullText += data.token;
                                onToken(data.token, fullText);
                            }
                            
                            if (data.done) {
                                console.log('🌊 Stream done signal received');
                            }
                            
                            if (data.error) {
                                throw new Error(data.error);
                            }
                        } catch (e) {
                            if (e.message !== 'Unexpected end of JSON input') {
                                console.warn('SSE parse error:', e);
                            }
                        }
                    }
                }
            }
        } catch (error) {
            // Don't report abort errors as failures
            if (error.name === 'AbortError') {
                console.log('🌊 Stream cancelled by user');
                return;
            }
            console.error('🌊 Stream error:', error);
            onError(error);
        } finally {
            this._currentAbortController = null;
        }
    },

    /**
     * Generate response using the Agentic Pipeline (multi-pass reasoning)
     * Automatically handles complexity detection, web search, and deep thinking
     * @param {string} prompt - User's question
     * @param {function} onToken - Called for each token received
     * @param {function} onPhase - Called when phase changes (with whimsical message)
     * @param {function} onDone - Called when generation completes
     * @param {function} onError - Called on error
     * @param {object} options - Optional settings
     */
    async generateAgent(prompt, onToken, onPhase, onDone, onError, options = {}) {
        const { temperature = 0.7, documentContext = null } = options;
        
        // Build context
        let contextMessages = [];
        if (State.contextMemory && State.contextMemory.length > 0) {
            contextMessages = State.contextMemory.slice(-CONFIG.CONTEXT_WINDOW_SIZE * 2);
        }
        
        const body = {
            prompt: prompt.trim(),
            temperature,
            principal: State.principal,
            context_messages: contextMessages,
            user_memory: State.userMemory || {},
        };
        
        if (documentContext) {
            body.document_context = documentContext;
        }
        
        const url = `${CONFIG.API_URL}/generate/agent`;
        console.log('🧠 Starting agent pipeline:', url);

        // Cancel any existing request before starting a new one
        this.cancelRequest();
        this._currentAbortController = new AbortController();
        const signal = this._currentAbortController.signal;

        try {
            const response = await fetch(url, {
                method: 'POST',
                mode: 'cors',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body),
                signal, // PERFORMANCE: Allow request cancellation
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let buffer = '';
            let agentResponse = null;
            
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) {
                    console.log('🧠 Agent stream complete:', fullText.length, 'chars');
                    onDone(fullText, agentResponse);
                    break;
                }
                
                // Decode chunk and add to buffer
                buffer += decoder.decode(value, { stream: true });
                
                // Process complete SSE messages from buffer
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            // Phase update - show whimsical loading message
                            if (data.phase && data.message) {
                                console.log(`🔄 Phase: ${data.phase} - ${data.message}`);
                                onPhase(data.phase, data.message);
                            }
                            
                            // Token - append to response
                            if (data.token) {
                                fullText += data.token;
                                onToken(data.token, fullText);
                            }
                            
                            // Clear signal - need to reset response (refinement)
                            if (data.clear) {
                                console.log('🔄 Clearing for refinement');
                                fullText = '';
                            }
                            
                            // Done - final response
                            if (data.done && data.response) {
                                agentResponse = data.response;
                                console.log('🧠 Agent complete:', {
                                    complexity: agentResponse.complexity,
                                    passes: agentResponse.passes_used,
                                    time: agentResponse.total_time_seconds,
                                    search: agentResponse.search_performed
                                });
                            }
                            
                            // Error
                            if (data.error) {
                                throw new Error(data.error);
                            }
                        } catch (e) {
                            if (e.message !== 'Unexpected end of JSON input') {
                                console.warn('SSE parse error:', e);
                            }
                        }
                    }
                }
            }
        } catch (error) {
            // Don't report abort errors as failures
            if (error.name === 'AbortError') {
                console.log('🧠 Agent request cancelled by user');
                return;
            }
            console.error('🧠 Agent error:', error);
            onError(error);
        } finally {
            this._currentAbortController = null;
        }
    },

    /**
     * Web search via Brave Search API
     * @param {string} query - Search query
     * @returns {Promise<{query: string, context: string, sources: Array}>}
     */
    async webSearch(query) {
        console.log('🔍 Web search:', query);
        const response = await this.request('/tools/search-and-summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, num_results: 3 })
        });
        return response;
    },

    // NEW ENDPOINTS FOR AUTOSAVE, ARCHIVE, ETC
    async autosave(chatData) {
        // Validate chat ID before sending
        if (!Validation.isValidChatId(State.currentChatId)) {
            console.error('❌ Invalid chat ID format:', State.currentChatId);
            throw new Error('Invalid chat ID format');
        }

        // Validate chat data structure
        const validation = Validation.validateChatData({
            chatId: State.currentChatId,
            messages: State.chatHistory
        });
        if (!validation.valid) {
            console.error('❌ Invalid chat data:', validation.error);
            throw new Error(validation.error);
        }

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
        if (!Validation.isValidChatId(chatId)) {
            console.error('❌ Invalid chat ID format:', chatId);
            throw new Error('Invalid chat ID format');
        }
        return this.request(`/chat/${chatId}`, { method: 'GET' });
    },

    async deleteChat(chatId) {
        if (!Validation.isValidChatId(chatId)) {
            console.error('❌ Invalid chat ID format:', chatId);
            throw new Error('Invalid chat ID format');
        }
        return this.request(`/chat/${chatId}`, { method: 'DELETE' });
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
                UI.updateConnectionStatus(true, data);
                console.log('✅ Successfully connected to Akash backend');
            } else {
                console.warn('Backend returned unhealthy status:', data);
                UI.updateConnectionStatus(false, null, 'Backend unhealthy');
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

            UI.updateConnectionStatus(false, null, detail);
        }
    },

    // Send message and get AI response via Agentic Pipeline
    async generate() {
        // SECURITY: Block if not authenticated
        if (!State.isAuthenticated) {
            console.warn('⛔ Generate blocked - user not authenticated');
            UI.showNotification('⛔ Please log in to use Trinity', 'error');
            return;
        }
        
        // Prevent double-submit
        if (State.isGenerating) return;

        let prompt = UI.elements.promptInput.value.trim();
        if (!prompt) return;

        // IMMEDIATELY mark as generating to prevent double-submit
        State.setGenerating(true);
        UI.setGenerating(true, State);

        // Clear input immediately to prevent re-submission
        const originalPrompt = prompt;
        UI.resetInput();

        // Initialize new chat if needed
        if (!State.chatStarted) {
            UI.showChatArea();
            State.setChatStarted(true);
            State.setCurrentChatId(State.generateChatId());
        }

        // Add user message
        State.addMessage('user', originalPrompt);
        UI.showMessage('user', originalPrompt);

        // Debug: Log current context
        console.log('📝 Current context memory:', State.contextMemory.length, 'messages');

        // Create AI message div immediately for streaming
        const { messagesContainer, chatArea } = UI.elements;
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        messageDiv.id = 'msg-' + Date.now();
        messagesContainer.appendChild(messageDiv);
        
        // Show whimsical thinking indicator initially
        // SECURITY: Use textContent for user-facing strings to prevent XSS
        const thinkingIndicator = document.createElement('div');
        thinkingIndicator.className = 'thinking-indicator';
        thinkingIndicator.innerHTML = `
            <span class="phase-badge">Thinking</span>
            <div class="thinking-message active">
                Examining the question<span class="thinking-dots"><span></span><span></span><span></span></span>
            </div>
        `;
        messageDiv.appendChild(thinkingIndicator);
        chatArea.scrollTop = chatArea.scrollHeight;

        try {
            let generatedText = '';
            let isReceivingTokens = false;

            console.log('🧠 Using Agentic Pipeline:', CONFIG.API_URL);

            // Agentic Pipeline for intelligent responses
            const documentContent = getAttachedContent();
            
            if (documentContent) {
                console.log('📎 Including attached content:', documentContent.length, 'chars');
            }
            
            // Token buffer for smoother typing effect
            let displayedLength = 0;
            let tokenBuffer = '';
            let typingInterval = null;

                // Helper to render KaTeX on message div (final pass only)
                // During streaming, math is pre-rendered via katex.renderToString() in parseMarkdownWithMath()
                // This renderKatex() is only called once at the end as a safety net
                const renderKatex = () => {
                    const renderFunc = window.renderMathInElement || (typeof renderMathInElement === 'function' ? renderMathInElement : null);
                    if (renderFunc) {
                        try {
                            renderFunc(messageDiv, {
                                delimiters: [
                                    { left: '$$', right: '$$', display: true },
                                    { left: '$', right: '$', display: false },
                                    { left: '\\[', right: '\\]', display: true },
                                    { left: '\\(', right: '\\)', display: false },
                                ],
                                throwOnError: false,
                                errorColor: '#cc0000',
                                strict: false,
                            });
                        } catch (e) {
                            // Ignore errors - math may be incomplete during streaming
                        }
                    }
                };

                // Smooth typing function - types out buffered text gradually
                const startTyping = () => {
                    if (typingInterval) return;
                    typingInterval = setInterval(() => {
                        if (displayedLength < tokenBuffer.length) {
                            // Type 2-5 characters at a time for smooth effect
                            const charsToAdd = Math.min(3, tokenBuffer.length - displayedLength);
                            displayedLength += charsToAdd;
                            const visibleText = tokenBuffer.substring(0, displayedLength);

                            // Set the HTML content with pre-rendered math
                            // parseMarkdownWithMath() uses katex.renderToString() to render math inline
                            // This avoids flashing - no need for post-render debouncedRenderKatex()
                            messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(visibleText)) +
                                '<span class="streaming-cursor">▊</span>';
                        }
                    }, 15); // ~66 chars/sec for natural typing feel
                };
                
                await new Promise((resolve, reject) => {
                    API.generateAgent(
                        prompt,
                        // onToken - buffer tokens for smooth typing
                        (token, fullText) => {
                            // First token - switch from thinking to response
                            if (!isReceivingTokens) {
                                isReceivingTokens = true;
                                messageDiv.innerHTML = '';
                                startTyping();
                            }
                            tokenBuffer = fullText;
                            generatedText = fullText;
                        },
                        // onPhase - update thinking indicator
                        (phase, message) => {
                            if (!isReceivingTokens) {
                                // SECURITY: Sanitize phase and message to prevent XSS
                                const phaseName = DOMPurify.sanitize(phase.charAt(0).toUpperCase() + phase.slice(1));
                                const safeMessage = DOMPurify.sanitize(message);
                                messageDiv.innerHTML = DOMPurify.sanitize(`
                                    <div class="thinking-indicator">
                                        <span class="phase-badge">${phaseName}</span>
                                        <div class="thinking-message active">
                                            ${safeMessage}<span class="thinking-dots"><span></span><span></span><span></span></span>
                                        </div>
                                    </div>
                                `);
                                chatArea.scrollTop = chatArea.scrollHeight;
                            }
                        },
                        // onDone - let typing finish, then render final with math
                        (fullText, agentResponse) => {
                            generatedText = fullText;
                            tokenBuffer = fullText; // Ensure buffer has full text
                            
                            // Wait for typing to catch up before final render
                            const finishTyping = () => {
                                if (displayedLength < tokenBuffer.length) {
                                    // Still typing - check again soon
                                    setTimeout(finishTyping, 20);
                                    return;
                                }
                                
                                // Typing caught up - stop interval and render final
                                if (typingInterval) {
                                    clearInterval(typingInterval);
                                    typingInterval = null;
                                }
                            
                                // Debug: Log if content contains potential math
                                if (fullText.includes('$') || fullText.includes('\\')) {
                                    console.log('📐 Math content detected:', fullText.substring(0, 200));
                                }
                            
                                messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(fullText));
                            
                                // Final KaTeX render
                                setTimeout(() => {
                                    renderKatex();
                                    console.log('✅ KaTeX final render complete');
                                }, 50);
                            
                                // Log agent stats
                                if (agentResponse) {
                                    console.log(`🧠 Agent: ${agentResponse.complexity} complexity, ${agentResponse.passes_used} passes, ${agentResponse.total_time_seconds}s`);
                                    if (agentResponse.search_performed) {
                                        console.log(`🔍 Web search performed: ${agentResponse.search_query}`);
                                    }
                                }
                                resolve();
                            };
                            
                            finishTyping();
                        },
                        // onError - handle failures
                        (error) => {
                            // Stop typing interval on error
                            if (typingInterval) {
                                clearInterval(typingInterval);
                                typingInterval = null;
                            }
                            reject(error);
                        },
                        { documentContext: documentContent }
                    );
                });
                
                // Clear attachment after sending
                clearAttachment();
                console.log('✅ Streamed text length:', generatedText.length);

            if (generatedText) {
                console.log('💬 Adding to state...');
                State.addMessage('assistant', generatedText);

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
                messageDiv.innerHTML = '❌ No response generated';
            }
        } catch (error) {
            console.error('❌ Generate error:', error);
            messageDiv.innerHTML = `❌ Request failed: ${error.message}`;
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
        
        // Clear UI and reset state
        UI.clearMessages();
        UI.resetInput();
        State.reset();
        
        // Ensure input is enabled
        if (UI.elements.promptInput) {
            UI.elements.promptInput.disabled = false;
        }
        if (UI.elements.submitButton) {
            UI.elements.submitButton.disabled = true; // Disabled until user types
        }
        
        // Enable attach button
        const attachBtn = document.getElementById('attachBtn');
        if (attachBtn) attachBtn.disabled = false;
        
        // Reset scroll position
        const chatArea = document.getElementById('chatArea');
        if (chatArea) chatArea.scrollTop = 0;
        
        UI.renderSidebar(State);
        console.log('🆕 New chat started');
    },

    // Toggle sidebar visibility
    toggleSidebar() {
        const sidebar = UI.elements.sidebar;
        const wasCollapsed = sidebar.classList.contains('collapsed');
        sidebar.classList.toggle('collapsed');

        // On mobile, set up click-outside-to-close after a small delay
        // to prevent the same click from immediately closing the sidebar
        if (window.innerWidth <= 768 && wasCollapsed) {
            // Sidebar is now open - add listener after this click event completes
            setTimeout(() => {
                document.addEventListener('click', this.closeSidebarOnClickOutside);
            }, 10);
        } else {
            document.removeEventListener('click', this.closeSidebarOnClickOutside);
        }
    },

    // Close sidebar when clicking outside (mobile)
    closeSidebarOnClickOutside(event) {
        const sidebar = UI.elements.sidebar;
        const toggleBtn = UI.elements.toggleSidebarBtn;
        const sidebarToggleBtn = UI.elements.sidebarToggleBtn;

        // Check if click is outside sidebar and both toggle buttons
        if (!sidebar.contains(event.target) && 
            !toggleBtn?.contains(event.target) && 
            !sidebarToggleBtn?.contains(event.target)) {
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
        
        // Retry any pending syncs from IndexedDB
        try {
            const { synced, failed } = await AutosaveManager.retryPendingSync(
                (chatData) => API.autosave(chatData)
            );
            if (synced > 0) {
                console.log(`☁️ Synced ${synced} pending chat(s)`);
            }
        } catch (error) {
            console.warn('⚠️ Failed to retry pending syncs:', error.message);
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
            
            const response = await API.listChats();
            const chats = response.chats || [];
            
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
            principal: State.principal,
            apiSave: (chatData) => API.autosave(chatData),
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

    // Recover archived chats from IPFS (auto-called on login)
    // NOTE: Archive feature was removed in v3.7.0 - this is now a no-op
    async recoverArchivedChats() {
        if (!State.isAuthenticated) {
            console.log('❌ recoverArchivedChats() skipped - not authenticated');
            return;
        }

        // Archive feature removed in v3.7.0 - skip recovery
        // Chats are now auto-saved directly to IPFS via autosave
        console.log('ℹ️ Archive recovery skipped (feature removed in v3.7.0)');
        return;

        // Legacy code below - kept for reference
        /*
        try {
            console.log('📦 Recovering archived chats from IPFS...');
            const response = await API.recoverArchives();

            if (!response.success) {
                console.log('ℹ️ No archives to recover:', response.message);
                return;
            }

            const archives = response.archives || [];
            console.log(`📦 Found ${archives.length} archived chats in IPFS`);

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
                        ipfsCID: archive.cid,
                        messageCount: archive.messageCount || 0,
                        recoveredFromIPFS: true
                    });
                    newCount++;
                }
            }

            if (newCount > 0) {
                console.log(`✅ Recovered ${newCount} new archived chats from IPFS`);
                UI.renderSidebar(State);
                UI.showNotification(`📦 Recovered ${newCount} archived chat(s) from IPFS`, 'success');
            } else {
                console.log('ℹ️ All archived chats already synced locally');
            }

        } catch (error) {
            console.error('❌ Failed to recover archives:', error);
            // Don't show error to user - this is a background operation
            // They can still use the app, just without recovered archives
        }
        */
    },

    // Load specific chat
    async loadChat(chatId) {
        // SECURITY: Block if not authenticated
        if (!State.isAuthenticated) {
            console.warn('⛔ Load chat blocked - user not authenticated');
            return;
        }
        
        try {
            const response = await API.loadChat(chatId);
            const chatData = response;
            
            State.setChatHistory(chatData.messages || []);
            State.setCurrentChatId(chatData.chatId || chatId);
            State.setChatStarted(true);
            
            // Rebuild context memory from last 6 messages
            State.setContextMemory([]);
            const recentMessages = State.chatHistory.slice(-State.CONTEXT_WINDOW_SIZE);
            recentMessages.forEach(msg => State.updateContextMemory(msg));
            console.log(`🔄 Loaded chat with ${State.chatHistory.length} messages, rebuilt context with ${State.contextMemory.length} recent messages`);
            
            UI.renderChatHistory(State);
            
            // Ensure input is enabled for all chats
            if (UI.elements.promptInput) UI.elements.promptInput.disabled = false;
            if (UI.elements.submitButton) UI.elements.submitButton.disabled = false;
            
            const attachBtn = document.getElementById('attachBtn');
            if (attachBtn) attachBtn.disabled = false;
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
            await API.deleteChat(chatId);
            
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
        CONFIG.setAPIURL(prodURL);
    } else if (preferredEnv === 'local' && localAvailable) {
        // User preference: local (and it's available)
        console.log('🔧 Using preferred LOCAL environment');
        CONFIG.setAPIURL('http://localhost:8000');
    } else if (preferredEnv === 'production') {
        // User preference: production
        console.log('🔧 Using preferred PRODUCTION environment');
        CONFIG.setAPIURL(prodURL);
    } else if (localAvailable) {
        // Default to local in development if available
        console.log('🔧 Defaulting to LOCAL environment');
        CONFIG.setAPIURL('http://localhost:8000');
    } else {
        // Fallback to production
        console.log('🔧 Using PRODUCTION environment');
        CONFIG.setAPIURL(prodURL);
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

    // Logout button in status header
    if (UI.elements.logoutBtn) {
        UI.elements.logoutBtn.addEventListener('click', () => Actions.logout());
    }

    // CID badge click handler
    const cidLink = document.getElementById('cidLink');
    if (cidLink) {
        cidLink.addEventListener('click', (e) => {
            e.preventDefault();
            const cid = cidLink.dataset.cid;
            if (cid) {
                Modals.showIPFSModal(cid);
            }
        });
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
        else if (action === 'deleteChat' && chatId) Actions.deleteChat(chatId);
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
        else if (action === 'showAbout') {
            Modals.showAboutModal();
        }
    });

    // Handle hover effects for chat items
    document.addEventListener('mouseover', (e) => {
        const chatItem = e.target.closest('.chat-item');
        if (!chatItem) return;
        chatItem.style.background = '#3d3d3d';
        const deleteBtn = chatItem.querySelector('.delete-btn');
        if (deleteBtn) deleteBtn.style.display = 'inline-block';
    });

    document.addEventListener('mouseout', (e) => {
        const chatItem = e.target.closest('.chat-item');
        if (!chatItem) return;
        chatItem.style.background = '#2d2d2d';
        const deleteBtn = chatItem.querySelector('.delete-btn');
        if (deleteBtn) deleteBtn.style.display = 'none';
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

    // Initialize file attachment tools
    initTools();
    console.log('✅ Tools initialized');

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
    console.log('AuthManager.isInitialized:', AuthManager.isInitialized);
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
