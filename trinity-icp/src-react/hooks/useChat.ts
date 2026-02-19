/**
 * useChat — SSE streaming with typed events, abort, retry.
 * Replaces ~300 lines across api.js + generate.js.
 *
 * Handles: token buffering, phase updates, abort via AbortController,
 * error handling, continuation (done_reason === 'length').
 */
import { useState, useCallback, useRef } from 'react';
import { useStore } from '../store';
import { streamSSE } from '../utils/sse';
import CONFIG from '../config';
import Logger from '../utils/logger';
import type { AgentResponse, AgentPhase, AuthHeaders } from '../types';

export interface UseChatReturn {
  /** Accumulated tokens from current stream */
  tokens: string;
  /** Whether a stream is currently active */
  isStreaming: boolean;
  /** Current agent phase (thinking, analyzing, etc.) */
  phase: AgentPhase | null;
  /** Last error from streaming */
  error: Error | null;
  /** Agent response metadata from last stream */
  agentResponse: AgentResponse | null;
  /** Get current tokens (ref-based, avoids stale closures) */
  getTokens: () => string;
  /** Send a prompt to the backend. Returns success/error to avoid stale closure issues. */
  send: (
    prompt: string,
    buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>
  ) => Promise<{
    success: boolean;
    error?: string;
    chatId?: string;
    assistantMessageId?: number | null;
  }>;
  /** Continue a truncated response */
  continueGeneration: (
    buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>
  ) => Promise<{
    success: boolean;
    error?: string;
    chatId?: string;
    assistantMessageId?: number | null;
  }>;
  /** Abort the current stream */
  stop: () => void;
  /** Clear error state */
  clearError: () => void;
}

export function useChat(): UseChatReturn {
  const [tokens, setTokens] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [phase, setPhase] = useState<AgentPhase | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [agentResponse, setAgentResponse] = useState<AgentResponse | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const tokensRef = useRef('');
  const sessionChatIdRef = useRef<string | null>(null);
  const assistantMessageIdRef = useRef<number | null>(null);

  /** Get current tokens (ref-based, avoids stale closures) */
  const getTokens = useCallback(() => tokensRef.current, []);

  const setGenerating = useStore((s) => s.setGenerating);

  /** Process SSE events from the stream */
  const processEvents = useCallback(
    async function* (
      response: Response,
      signal: AbortSignal
    ): AsyncGenerator<void, void, unknown> {
      for await (const event of streamSSE(response, signal)) {
        if (event.type === 'session' && event.chat_id) {
          sessionChatIdRef.current = event.chat_id;
          useStore.setState({ currentChatId: event.chat_id });
        }

        // Phase updates
        if (event.phase) {
          setPhase({ name: event.phase, message: event.message });
        }

        // Token updates
        if (event.token) {
          tokensRef.current += event.token;
          setTokens(tokensRef.current);
        }

        // Completion
        if (event.done) {
          assistantMessageIdRef.current = event.assistant_message_id ?? null;
          const agentResp: AgentResponse = {
            done_reason: event.done_reason ?? 'stop',
            ...(event.response ?? {}),
          };
          setAgentResponse(agentResp);
          // Unlock UI immediately on protocol-level completion.
          // Socket teardown can lag briefly after final token/done event.
          setIsStreaming(false);
          setGenerating(false);
          return;
        }

        // Error from backend
        if (event.error) {
          setError(new Error(event.error));
        }

        yield;
      }
    },
    []
  );

  /** Send a prompt to the agent endpoint */
  const send = useCallback(
    async (
      prompt: string,
      buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>
    ): Promise<{
      success: boolean;
      error?: string;
      chatId?: string;
      assistantMessageId?: number | null;
    }> => {
      // Reset state
      abortRef.current = new AbortController();
      setIsStreaming(true);
      setTokens('');
      setPhase(null);
      setError(null);
      setAgentResponse(null);
      tokensRef.current = '';
      sessionChatIdRef.current = null;
      assistantMessageIdRef.current = null;
      setGenerating(true);

      try {
        const headers = await buildAuthHeaders('/generate/agent');
        if (!headers) throw new Error('Authentication required');

        const state = useStore.getState();

        const body = {
          prompt,
          chat_id: state.currentChatId ?? undefined,
        };

        const response = await fetch(`${CONFIG.API_URL}/generate/agent`, {
          method: 'POST',
          signal: abortRef.current.signal,
          headers,
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          // Handle rate limiting
          if (response.status === 429) {
            const data = await response.json().catch(() => ({}));
            throw new Error(
              `Rate limited. ${data.retry_after ? `Retry in ${Math.ceil(data.retry_after)}s` : 'Please wait.'}`
            );
          }
          throw new Error(`Request failed: ${response.status} ${response.statusText}`);
        }

        // Process the event stream
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        for await (const _event of processEvents(response, abortRef.current.signal)) {
          // Events processed by processEvents
        }

        return {
          success: true,
          chatId: sessionChatIdRef.current ?? (useStore.getState().currentChatId ?? undefined),
          assistantMessageId: assistantMessageIdRef.current,
        };
      } catch (e) {
        const err = e as Error;
        if (err.name !== 'AbortError') {
          setError(err);
          Logger.error('Chat send error:', err);
          return { success: false, error: err.message };
        }
        return { success: false, error: 'Aborted' };
      } finally {
        setIsStreaming(false);
        setGenerating(false);
        abortRef.current = null;
      }
    },
    [setGenerating, processEvents]
  );

  /** Continue from a truncated response (done_reason === 'length') */
  const continueGeneration = useCallback(
    async (
      buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>
    ): Promise<{
      success: boolean;
      error?: string;
      chatId?: string;
      assistantMessageId?: number | null;
    }> => {
      const previousText = tokensRef.current;
      if (!previousText) return { success: false, error: 'No previous text' };

      // Continue with a prompt that includes the previous text
      const continuePrompt = `Continue from where you left off. Your previous response ended with: "${previousText.slice(-200)}"`;

      abortRef.current = new AbortController();
      setIsStreaming(true);
      setPhase(null);
      setError(null);
      setAgentResponse(null);
      sessionChatIdRef.current = null;
      assistantMessageIdRef.current = null;
      setGenerating(true);

      try {
        const headers = await buildAuthHeaders('/generate/agent');
        if (!headers) throw new Error('Authentication required');

        const state = useStore.getState();

        const body = {
          prompt: continuePrompt,
          chat_id: state.currentChatId ?? undefined,
        };

        const response = await fetch(`${CONFIG.API_URL}/generate/agent`, {
          method: 'POST',
          signal: abortRef.current.signal,
          headers,
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }

        // Merge with previous output
        for await (const event of streamSSE(response, abortRef.current.signal)) {
          if (event.type === 'session' && event.chat_id) {
            sessionChatIdRef.current = event.chat_id;
            useStore.setState({ currentChatId: event.chat_id });
          }
          if (event.token) {
            tokensRef.current += event.token;
            setTokens(tokensRef.current);
          }
          if (event.done) {
            assistantMessageIdRef.current = event.assistant_message_id ?? null;
            setAgentResponse({
              done_reason: event.done_reason ?? 'stop',
              ...(event.response ?? {}),
            });
            // Same immediate unlock behavior as send().
            setIsStreaming(false);
            setGenerating(false);
            break;
          }
          if (event.error) setError(new Error(event.error));
        }

        return {
          success: true,
          chatId: sessionChatIdRef.current ?? (useStore.getState().currentChatId ?? undefined),
          assistantMessageId: assistantMessageIdRef.current,
        };
      } catch (e) {
        const err = e as Error;
        if (err.name !== 'AbortError') {
          setError(err);
          return { success: false, error: err.message };
        }
        return { success: false, error: 'Aborted' };
      } finally {
        setIsStreaming(false);
        setGenerating(false);
        abortRef.current = null;
      }
    },
    [setGenerating]
  );

  /** Abort current stream */
  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  /** Clear error state */
  const clearError = useCallback(() => setError(null), []);

  return {
    tokens,
    isStreaming,
    phase,
    error,
    agentResponse,
    getTokens,
    send,
    continueGeneration,
    stop,
    clearError,
  };
}

export default useChat;
