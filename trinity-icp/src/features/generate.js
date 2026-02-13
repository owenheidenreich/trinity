// ============================================================================
// FEATURE: GENERATE — AI message generation and streaming
// ============================================================================
// Handles: generate (agentic pipeline), stop, edit-and-regenerate, health check.
// ============================================================================

import CONFIG from '../config.js';
import API from '../core/api.js';
import State from '../state/store.js';
import UI from '../ui/index.js';
import ContextMemory from '../state/contextMemory.js';
import AutosaveManager from '../storage/autosave.js';
import { enhanceCodeBlocks, addCopyAllButton, addContinueButton, addDownloadSection } from '../ui/messages.js';
import { extractCodeBlocks, getCodeBlockStatus } from '../utils/codeBlockParser.js';
import { getFileIcon, LANG_EXTENSIONS, generateSmartFilename } from '../utils/codeUtils.js';
import { addEditButton, parseMarkdownWithMath, preprocessToolCalls } from '../ui/editMessage.js';
import { getAttachedContent, clearAttachment } from '../tools.js';
import { healthCheckViaCanister, isCanisterConfigured } from '../api/canister-client.js';

/**
 * Check backend connection health.
 */
export async function checkConnection() {
    try {
        let data;

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
}

/**
 * Send message and get AI response via Agentic Pipeline.
 * @param {function} executeAutosave - Callback for autosave execution
 */
export async function generate(executeAutosave) {
    // Block if not authenticated
    if (!State.isAuthenticated) {
        console.warn('⛔ Generate blocked - user not authenticated');
        UI.showNotification('⛔ Please log in to use Trinity', 'error');
        return;
    }

    // Prevent double-submit
    if (State.isGenerating) return;

    let prompt = UI.elements.promptInput.value.trim();
    if (!prompt) return;

    // Mark as generating immediately
    State.setGenerating(true);
    UI.setGenerating(true, State);

    // Clear input immediately
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
    const userMsgId = UI.showMessage('user', originalPrompt);

    // Add edit button
    const userMsgDiv = document.getElementById(userMsgId);
    if (userMsgDiv) {
        addEditButton(userMsgDiv, originalPrompt, null, editAndRegenerate);
    }

    console.log('📝 Current context memory:', State.contextMemory.length, 'messages');

    // Create AI message div for streaming
    const { messagesContainer, chatArea } = UI.elements;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ai';
    messageDiv.id = 'msg-' + Date.now();
    messagesContainer.appendChild(messageDiv);

    // Show thinking indicator
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

        const documentContent = getAttachedContent();
        if (documentContent) {
            console.log('📎 Including attached content:', documentContent.length, 'chars');
        }

        // Token buffer for smooth typing effect
        let displayedLength = 0;
        let tokenBuffer = '';
        let typingInterval = null;

        // KaTeX final render helper
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
                    // Ignore — math may be incomplete during streaming
                }
            }
        };

        // Track code blocks detected during streaming
        let lastBlockCount = 0;

        // Stable/stream/tail DOM split:
        // stableDiv  – completed code blocks (updated only when a new block completes)
        // streamDiv  – persistent <details> for the in-progress code block (never destroyed per-tick)
        // tailDiv    – trailing prose + cursor (innerHTML replaced every tick)
        let stableDiv = null;
        let streamDiv = null;
        let tailDiv = null;

        // Persistent DOM refs for the streaming code card
        let streamDetailsEl = null;
        let streamCodeEl = null;
        let streamSummaryTextEl = null;

        // Smooth typing function
        const startTyping = () => {
            if (typingInterval) return;

            // Create stable + tail + stream containers
            // Order: stableDiv (completed blocks) → tailDiv (trailing prose) → streamDiv (in-progress code card)
            // This keeps the streaming card below the prose that precedes it
            stableDiv = document.createElement('div');
            tailDiv = document.createElement('div');
            streamDiv = document.createElement('div');
            messageDiv.appendChild(stableDiv);
            messageDiv.appendChild(tailDiv);
            messageDiv.appendChild(streamDiv);

            typingInterval = setInterval(() => {
                if (displayedLength < tokenBuffer.length) {
                    const charsToAdd = Math.min(3, tokenBuffer.length - displayedLength);
                    displayedLength += charsToAdd;
                    const visibleText = tokenBuffer.substring(0, displayedLength);

                    // Detect code blocks during streaming
                    const status = getCodeBlockStatus(visibleText);

                    // If there's an in-progress code block, hide the raw code
                    // by truncating at the last unclosed fence
                    let textToRender = visibleText;

                    if (status.inProgress) {
                        const lastFence = visibleText.lastIndexOf('```');
                        if (lastFence >= 0) {
                            textToRender = visibleText.substring(0, lastFence);
                        }
                        const lang = status.partialLang || 'code';
                        const lineCount = status.partialCode
                            ? status.partialCode.split('\n').filter(l => l.trim()).length
                            : 0;
                        const icon = getFileIcon(lang);
                        const ext = LANG_EXTENSIONS[lang.toLowerCase()] || 'txt';

                        // Create persistent <details> element ONCE
                        if (!streamDetailsEl) {
                            streamDetailsEl = document.createElement('details');
                            streamDetailsEl.className = 'code-details code-streaming-indicator';
                            streamDetailsEl.open = false;  // Write collapsed — user can expand if curious

                            const summary = document.createElement('summary');
                            summary.className = 'code-details-summary';

                            const iconSpan = document.createElement('span');
                            iconSpan.className = 'code-details-icon';
                            iconSpan.textContent = icon;

                            streamSummaryTextEl = document.createElement('span');
                            streamSummaryTextEl.className = 'code-details-text';

                            const tagSpan = document.createElement('span');
                            tagSpan.className = 'code-details-tag';
                            tagSpan.textContent = ext.toUpperCase();

                            summary.appendChild(iconSpan);
                            summary.appendChild(streamSummaryTextEl);
                            summary.appendChild(tagSpan);
                            streamDetailsEl.appendChild(summary);

                            const pre = document.createElement('pre');
                            streamCodeEl = document.createElement('code');
                            if (lang && lang !== 'code') {
                                streamCodeEl.className = `language-${lang}`;
                            }
                            pre.appendChild(streamCodeEl);
                            streamDetailsEl.appendChild(pre);

                            streamDiv.appendChild(streamDetailsEl);
                        }

                        // Update ONLY text content (no DOM destruction)
                        streamSummaryTextEl.textContent = `Writing ${lang}… · ${lineCount} line${lineCount !== 1 ? 's' : ''}`;
                        streamCodeEl.textContent = status.partialCode || '';
                    } else if (streamDetailsEl) {
                        // Code block just completed — clear the streaming card
                        streamDiv.innerHTML = '';
                        streamDetailsEl = null;
                        streamCodeEl = null;
                        streamSummaryTextEl = null;
                    }

                    // Find where completed code blocks end in the raw text
                    let stableEnd = 0;
                    if (status.complete > 0) {
                        const fenceRegex = /```\S*(?::\S+)?\s*\n[\s\S]*?```/g;
                        let match;
                        while ((match = fenceRegex.exec(textToRender)) !== null) {
                            stableEnd = match.index + match[0].length;
                        }
                        if (stableEnd < textToRender.length && textToRender[stableEnd] === '\n') stableEnd++;
                    }

                    // Update stable section ONLY when a new block completes
                    if (status.complete > lastBlockCount) {
                        const prevOpen = new Set();
                        stableDiv.querySelectorAll('details.code-details').forEach((d, i) => {
                            if (d.open) prevOpen.add(i);
                        });

                        lastBlockCount = status.complete;
                        const stableText = textToRender.substring(0, stableEnd);
                        const tempDiv = document.createElement('div');
                        tempDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(stableText));
                        try {
                            const blocks = extractCodeBlocks(stableText);
                            enhanceCodeBlocks(tempDiv, blocks, { highlight: true });
                        } catch (e) { /* ignore during streaming */ }
                        stableDiv.innerHTML = tempDiv.innerHTML;

                        stableDiv.querySelectorAll('details.code-details').forEach((d, i) => {
                            // Keep completed blocks collapsed by default during streaming
                            if (prevOpen.has(i)) d.open = true;
                            else d.open = false;
                        });
                    }

                    // Update tail section every tick (only text after last completed block)
                    const tailText = stableEnd > 0 ? textToRender.substring(stableEnd) : textToRender;
                    tailDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(tailText)) +
                        '<span class="streaming-cursor">▊</span>';

                    // Auto-scroll to keep new content visible
                    chatArea.scrollTop = chatArea.scrollHeight;
                }
            }, 15);
        };

        await new Promise((resolve, reject) => {
            API.generateAgent(
                prompt,
                // onToken
                (token, fullText) => {
                    if (!isReceivingTokens) {
                        isReceivingTokens = true;
                        messageDiv.innerHTML = '';
                        startTyping();
                    }
                    tokenBuffer = fullText;
                    generatedText = fullText;
                },
                // onPhase
                (phase, message) => {
                    if (!isReceivingTokens) {
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
                // onDone
                (fullText, agentResponse) => {
                    generatedText = fullText;
                    tokenBuffer = fullText;

                    const finishTyping = () => {
                        if (displayedLength < tokenBuffer.length) {
                            setTimeout(finishTyping, 20);
                            return;
                        }

                        if (typingInterval) {
                            clearInterval(typingInterval);
                            typingInterval = null;
                        }

                        if (fullText.includes('$') || fullText.includes('\\')) {
                            console.log('📐 Math content detected:', fullText.substring(0, 200));
                        }

                        messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(fullText));
                        
                        // Extract final code blocks and render
                        const finalBlocks = extractCodeBlocks(fullText);
                        try { enhanceCodeBlocks(messageDiv, finalBlocks); } catch (e) { console.error('Code enhancement failed:', e); }
                        
                        // Add download section for code blocks
                        if (finalBlocks.length > 0) {
                            addDownloadSection(messageDiv, finalBlocks);
                        }
                        
                        // Store raw text for Copy All
                        messageDiv.dataset.rawText = fullText;
                        
                        // Add Copy All button at bottom
                        addCopyAllButton(messageDiv);

                        // Final scroll to bottom
                        chatArea.scrollTop = chatArea.scrollHeight;

                        // If response was truncated, show Continue button
                        if (agentResponse?.done_reason === 'length') {
                            console.log('⚠️ Response truncated — showing Continue button');
                            addContinueButton(messageDiv, () => {
                                // Build continuation prompt
                                const lastChars = fullText.slice(-300);
                                const continuePrompt = `Continue your previous response exactly from where you left off. Do NOT repeat anything. Your last output ended with:\n\n"${lastChars}"\n\nContinue seamlessly from that exact point:`;

                                // Stream continuation into the same messageDiv
                                let continuationText = '';
                                let continueBuffer = '';
                                let continueDisplayed = 0;
                                let continueInterval = null;

                                // Remove the continue button and copy-all button
                                const continueBtn = messageDiv.querySelector('.continue-btn');
                                const copyAllBtn = messageDiv.querySelector('.copy-all-btn');
                                const downloadSection = messageDiv.querySelector('.message-downloads');
                                if (continueBtn) continueBtn.remove();
                                if (copyAllBtn) copyAllBtn.remove();
                                if (downloadSection) downloadSection.remove();

                                // Create a continuation container at the end
                                const contDiv = document.createElement('div');
                                contDiv.className = 'continuation-stream';
                                messageDiv.appendChild(contDiv);

                                const startContinueTyping = () => {
                                    continueInterval = setInterval(() => {
                                        if (continueDisplayed < continueBuffer.length) {
                                            const chars = Math.min(3, continueBuffer.length - continueDisplayed);
                                            continueDisplayed += chars;
                                            const visible = continueBuffer.substring(0, continueDisplayed);
                                            contDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(visible)) + '<span class="streaming-cursor">\u258a</span>';
                                        }
                                    }, 15);
                                };

                                API.generateAgent(
                                    continuePrompt,
                                    // onToken
                                    (token, ft) => {
                                        if (!continueInterval) startContinueTyping();
                                        continueBuffer = ft;
                                        continuationText = ft;
                                    },
                                    // onPhase (ignore for continuation)
                                    () => {},
                                    // onDone
                                    (contText, contAgentResp) => {
                                        const finishCont = () => {
                                            if (continueDisplayed < continueBuffer.length) {
                                                setTimeout(finishCont, 20);
                                                return;
                                            }
                                            if (continueInterval) {
                                                clearInterval(continueInterval);
                                                continueInterval = null;
                                            }

                                            // Merge: re-render entire combined response
                                            const combined = fullText + '\n' + contText;
                                            messageDiv.innerHTML = DOMPurify.sanitize(parseMarkdownWithMath(combined));
                                            const allBlocks = extractCodeBlocks(combined);
                                            try { enhanceCodeBlocks(messageDiv, allBlocks); } catch(e) {}
                                            if (allBlocks.length > 0) addDownloadSection(messageDiv, allBlocks);
                                            messageDiv.dataset.rawText = combined;
                                            addCopyAllButton(messageDiv);

                                            // Update chat history with merged content
                                            const history = State.chatHistory;
                                            if (history.length > 0) {
                                                const lastMsg = history[history.length - 1];
                                                if (lastMsg.role === 'assistant') {
                                                    lastMsg.content = combined;
                                                    State.setChatHistory([...history]);
                                                }
                                            }

                                            // If still truncated, show Continue again
                                            if (contAgentResp?.done_reason === 'length') {
                                                // Update fullText closure for potential chained continues
                                                fullText = combined;
                                                addContinueButton(messageDiv, arguments.callee);
                                            }

                                            renderKatex();
                                        };
                                        finishCont();
                                    },
                                    // onError
                                    (err) => {
                                        if (continueInterval) clearInterval(continueInterval);
                                        console.error('Continue error:', err);
                                        contDiv.innerHTML += '<p style="color:#ef4444;">Failed to continue. Please try again.</p>';
                                    },
                                    { documentContext: null }
                                );
                            });
                        }

                        setTimeout(() => {
                            renderKatex();
                            console.log('✅ KaTeX final render complete');
                        }, 50);

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
                // onError
                (error) => {
                    if (typingInterval) {
                        clearInterval(typingInterval);
                        typingInterval = null;
                    }
                    reject(error);
                },
                { documentContext: documentContent }
            );
        });

        clearAttachment();
        console.log('✅ Streamed text length:', generatedText.length);

        if (generatedText) {
            console.log('💬 Adding to state...');
            const cleanText = preprocessToolCalls(generatedText);
            State.addMessage('assistant', cleanText);

            // Check if summarization is needed
            if (State.chatHistory.length >= State.SUMMARY_INTERVAL &&
                State.chatHistory.length - State.lastSummaryAt >= State.SUMMARY_INTERVAL) {
                console.log(`📊 Conversation has ${State.chatHistory.length} messages, triggering summarization...`);
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
                    () => executeAutosave()
                );
            }
        } else {
            console.error('❌ No generated text received');
            messageDiv.innerHTML = '❌ No response generated';
        }
    } catch (error) {
        if (error.name === 'AbortError' || error.isAbort) {
            console.log('🛑 Generation aborted by user');
            return;
        }
        console.error('❌ Generate error:', error);
        messageDiv.innerHTML = `❌ Request failed: ${error.message}`;
    } finally {
        UI.setGenerating(false, State);
    }
}

/**
 * Stop current generation.
 */
export function stopGeneration() {
    API.cancelRequest();
    State.setGenerating(false);
    UI.setGenerating(false, State);

    const messagesContainer = UI.elements.messagesContainer;
    const lastAiMessage = messagesContainer.querySelector('.message.ai:last-of-type');
    if (lastAiMessage) {
        const hasContent = lastAiMessage.textContent.trim().length > 50;
        if (!hasContent) {
            lastAiMessage.remove();
            const lastMsg = State.chatHistory[State.chatHistory.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
                State.removeLastMessage();
            }
        }
    }

    UI.showNotification('Generation stopped', 'info');
}

/**
 * Edit a user message and regenerate from that point.
 */
export async function editAndRegenerate(userMsgIndex, newContent) {
    const userMessages = State.chatHistory.filter(m => m.role === 'user');
    if (userMsgIndex < 0 || userMsgIndex >= userMessages.length) return;

    // Find actual index in chatHistory
    let count = -1;
    let actualIndex = -1;
    for (let i = 0; i < State.chatHistory.length; i++) {
        if (State.chatHistory[i].role === 'user') {
            count++;
            if (count === userMsgIndex) {
                actualIndex = i;
                break;
            }
        }
    }

    if (actualIndex < 0) return;

    // Truncate chat history from this point
    const newHistory = State.chatHistory.slice(0, actualIndex);
    State.setChatHistory(newHistory);

    // Rebuild context memory
    const contextSize = State.CONTEXT_WINDOW_SIZE;
    const newContext = newHistory.slice(-contextSize);
    State.setContextMemory(newContext);

    // Clear and re-render
    UI.clearMessages();
    UI.showChatArea();

    if (newHistory.length > 0) {
        newHistory.forEach(msg => {
            const msgId = UI.showMessage(msg.role === 'assistant' ? 'ai' : 'user', msg.content);
            if (msg.role === 'user') {
                const msgDiv = document.getElementById(msgId);
                if (msgDiv) addEditButton(msgDiv, msg.content, null, editAndRegenerate);
            }
        });
    }

    // Set new content and generate
    UI.elements.promptInput.value = newContent;
    // Note: generate() is called via the module's own export
    await generate(null); // no autosave callback needed for edit-regenerate
}
