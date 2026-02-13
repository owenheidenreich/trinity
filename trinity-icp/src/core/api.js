// ============================================================================
// CORE API LAYER — All backend communication
// ============================================================================
// Handles signed requests, streaming, rate-limit UX, and all endpoint calls.
// Every fetch() in the frontend goes through this module.
// ============================================================================

import CONFIG from '../config.js';
import State from '../state/store.js';
import AuthManager from '../auth/authManager.js';
import UI from '../ui/index.js';
import Validation from '../utils/validation.js';
import { generateViaCanister, isCanisterConfigured } from '../api/canister-client.js';

const API = {
    // AbortController for cancelling in-flight requests
    _currentAbortController: null,

    /**
     * Cancel any ongoing API request (streaming or regular)
     */
    cancelRequest() {
        if (this._currentAbortController) {
            this._currentAbortController.abort();
            this._currentAbortController = null;
        }
    },

    async request(endpoint, options = {}) {
        const url = `${CONFIG.API_URL}${endpoint}`;

        // Start with session-aware headers
        const headers = {
            ...CONFIG.getApiHeaders(),
            'Accept': 'application/json',
            ...options.headers
        };

        // Add ICP authentication headers if authenticated
        if (State.isAuthenticated && AuthManager.isInitialized) {
            try {
                const timestamp = Date.now().toString();
                const nonce = crypto.randomUUID();
                const message = `${State.principal}:${timestamp}:${endpoint}:${nonce}`;
                const signature = await AuthManager.signMessage(message);
                const publicKey = AuthManager.getPublicKeyHex();

                if (signature && publicKey) {
                    headers['ICP-Principal'] = State.principal;
                    headers['ICP-Signature'] = signature;
                    headers['ICP-Timestamp'] = timestamp;
                    headers['ICP-PublicKey'] = publicKey;
                    headers['ICP-Nonce'] = nonce;

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
                // Handle rate limiting with countdown
                if (response.status === 429) {
                    let retryAfter = 60;
                    try {
                        const errorData = await response.json();
                        retryAfter = errorData?.error?.retry_after_seconds || parseInt(response.headers.get('Retry-After')) || 60;
                    } catch { /* use default */ }
                    try {
                        UI.showRateLimitCountdown(retryAfter);
                    } catch (uiErr) {
                        console.warn('⚠️ Could not show rate limit UI:', uiErr.message);
                    }
                    throw new Error('Rate limit exceeded');
                }

                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`);
            }

            // Check rate limit warning (80% threshold)
            const remaining = response.headers.get('X-RateLimit-Remaining');
            const limit = response.headers.get('X-RateLimit-Limit');
            if (remaining && limit) {
                const ratio = parseInt(remaining) / parseInt(limit);
                if (ratio < 0.2 && ratio > 0) {
                    UI.showWarning(`Slow down - only ${remaining} requests left this minute`);
                }
            }

            return response.json();
        } catch (error) {
            console.error(`❌ Request failed to ${url}:`, error);
            throw error;
        }
    },

    async healthCheck() {
        // Use simple fetch — /health is public, no auth headers needed.
        // Avoids CORS preflight issues with custom ICP-* headers.
        const response = await fetch(`${CONFIG.API_URL}/health`, {
            method: 'GET',
            mode: 'cors',
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    },

    /**
     * Simple generate — minimal path, no context/auth complexity
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
            max_length: 800,
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

        return {
            generated_text: result.response || result.generated_text,
            model: result.model,
            provider_id: result.provider_id,
            done: result.done
        };
    },

    /**
     * Generate with streaming — tokens appear as they're generated
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
            max_length: reasoningMode ? 4000 : 1000,
            temperature,
            principal: State.principal,
            contextMemory: contextMessages,
            reasoning_mode: reasoningMode,
        };

        if (documentContext) {
            body.documentContext = documentContext;
        }

        const url = `${CONFIG.API_URL}/generate/stream`;
        console.log('🌊 Starting stream:', url);

        this.cancelRequest();
        this._currentAbortController = new AbortController();
        const signal = this._currentAbortController.signal;

        try {
            const response = await fetch(url, {
                method: 'POST',
                mode: 'cors',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let buffer = '';

            while (true) {
                const { done, value } = await Promise.race([
                    reader.read(),
                    new Promise((_, reject) => {
                        if (signal.aborted) {
                            reject(new DOMException('Stream aborted by user', 'AbortError'));
                        }
                        signal.addEventListener('abort', () => {
                            console.log('🛑 Stream aborted - stopping reader');
                            reader.cancel();
                            reject(new DOMException('Stream aborted by user', 'AbortError'));
                        }, { once: true });
                    })
                ]);

                if (done) {
                    console.log('🌊 Stream complete:', fullText.length, 'chars');
                    onDone(fullText);
                    break;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

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
     * Generate via Agentic Pipeline (multi-pass reasoning)
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

        this.cancelRequest();
        this._currentAbortController = new AbortController();
        const signal = this._currentAbortController.signal;

        try {
            const response = await fetch(url, {
                method: 'POST',
                mode: 'cors',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal,
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
                const { done, value } = await Promise.race([
                    reader.read(),
                    new Promise((_, reject) => {
                        if (signal.aborted) {
                            reject(new DOMException('Stream aborted by user', 'AbortError'));
                        }
                        signal.addEventListener('abort', () => {
                            console.log('🛑 Agent stream aborted by user');
                            reader.cancel();
                            reject(new DOMException('Stream aborted by user', 'AbortError'));
                        }, { once: true });
                    })
                ]);

                if (done) {
                    console.log('🧠 Agent stream complete:', fullText.length, 'chars');
                    onDone(fullText, agentResponse);
                    break;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.phase && data.message) {
                                console.log(`🔄 Phase: ${data.phase} - ${data.message}`);
                                onPhase(data.phase, data.message);
                            }

                            if (data.token) {
                                fullText += data.token;
                                onToken(data.token, fullText);
                            }

                            if (data.clear) {
                                console.log('🔄 Clearing for refinement');
                                fullText = '';
                            }

                            if (data.done && data.response) {
                                agentResponse = data.response;
                                // Capture done_reason for truncation detection
                                if (data.done_reason) {
                                    agentResponse.done_reason = data.done_reason;
                                }
                                console.log('🧠 Agent complete:', {
                                    complexity: agentResponse.complexity,
                                    passes: agentResponse.passes_used,
                                    time: agentResponse.total_time_seconds,
                                    search: agentResponse.search_performed
                                });
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
            if (error.name === 'AbortError') {
                console.log('🧠 Agent request cancelled by user');
                const abortError = new Error('Request aborted');
                abortError.name = 'AbortError';
                abortError.isAbort = true;
                onError(abortError);
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

    // Chat persistence endpoints
    async autosave(chatData) {
        if (!Validation.isValidChatId(State.currentChatId)) {
            console.error('❌ Invalid chat ID format:', State.currentChatId);
            throw new Error('Invalid chat ID format');
        }

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

export default API;
