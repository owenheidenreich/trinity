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
import Logger from './logger.js';
import { streamSSE } from './sse.js';

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

                    Logger.debug('Request signed for', endpoint);
                }
            } catch (error) {
                Logger.warn('Failed to sign request:', error);
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
                        Logger.warn('Could not show rate limit UI:', uiErr.message);
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
            Logger.error(`Request failed to ${url}:`, error);
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
     * Generate via Agentic Pipeline (single-pass with streaming)
     */
    async generateAgent(prompt, onToken, onPhase, onDone, onError, options = {}) {
        const { temperature = 0.7, documentContext = null } = options;

        // Build context — use CONTEXT_WINDOW_SIZE directly (no multiplier)
        let contextMessages = [];
        if (State.contextMemory && State.contextMemory.length > 0) {
            contextMessages = State.contextMemory.slice(-State.CONTEXT_WINDOW_SIZE);
        }

        const body = {
            prompt: prompt.trim(),
            temperature,
            principal: State.principal,
            context_messages: contextMessages,
            user_memory: State.userMemory || {},
            chat_id: State.currentChatId,
            message_index: State.chatHistory.length,
        };

        if (documentContext) {
            body.document_context = documentContext;
        }

        const url = `${CONFIG.API_URL}/generate/agent`;
        Logger.debug('Starting agent pipeline:', url);

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

            let fullText = '';
            let agentResponse = null;

            for await (const data of streamSSE(response, signal)) {
                if (data.phase && data.message) {
                    Logger.debug(`Phase: ${data.phase} - ${data.message}`);
                    onPhase(data.phase, data.message);
                }

                if (data.token) {
                    fullText += data.token;
                    onToken(data.token, fullText);
                }

                if (data.done && data.response) {
                    agentResponse = data.response;
                    if (data.done_reason) {
                        agentResponse.done_reason = data.done_reason;
                    }
                    Logger.debug('Agent complete:', {
                        passes: agentResponse.passes_used,
                        time: agentResponse.total_time_seconds,
                    });
                }

                if (data.error) {
                    throw new Error(data.error);
                }
            }

            onDone(fullText, agentResponse);
        } catch (error) {
            if (error.name === 'AbortError') {
                Logger.debug('Agent request cancelled by user');
                const abortError = new Error('Request aborted');
                abortError.name = 'AbortError';
                abortError.isAbort = true;
                onError(abortError);
                return;
            }
            Logger.error('Agent error:', error);
            onError(error);
        } finally {
            this._currentAbortController = null;
        }
    },

    /**
     * Web search via Brave Search API
     */
    async webSearch(query) {
        Logger.debug('Web search:', query);
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
            Logger.error('Invalid chat ID format:', State.currentChatId);
            throw new Error('Invalid chat ID format');
        }

        const validation = Validation.validateChatData({
            chatId: State.currentChatId,
            messages: State.chatHistory
        });
        if (!validation.valid) {
            Logger.error('Invalid chat data:', validation.error);
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

        Logger.debug('Autosave:', payload.chatId, payload.messages.length, 'messages');

        try {
            const response = await this.request('/chat/autosave', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            Logger.debug('Autosave saved successfully');
            return response;
        } catch (error) {
            Logger.error('Autosave failed:', error.message);
            throw error;
        }
    },

    async listChats() {
        return this.request('/chat/list', { method: 'GET' });
    },

    async loadChat(chatId) {
        if (!Validation.isValidChatId(chatId)) {
            Logger.error('Invalid chat ID format:', chatId);
            throw new Error('Invalid chat ID format');
        }
        return this.request(`/chat/${chatId}`, { method: 'GET' });
    },

    async deleteChat(chatId) {
        if (!Validation.isValidChatId(chatId)) {
            Logger.error('Invalid chat ID format:', chatId);
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
