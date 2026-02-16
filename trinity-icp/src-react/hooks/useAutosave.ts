/**
 * useAutosave — 2s debounced encrypted autosave with exponential backoff.
 * Ported from storage/autosave.js as a React hook.
 */
import { useCallback, useRef } from 'react';
import { useStore } from '../store';
import { IndexedDBStorage } from '../utils/indexedDB';
import CONFIG from '../config';
import Logger from '../utils/logger';
import type { AuthHeaders, ChatMessage } from '../types';

const DEBOUNCE_MS = 2_000;
const MAX_RETRIES = 5;
const RETRY_BASE_MS = 1_000;
const RETRY_BACKOFF = 2;

export function useAutosave(onSaveSuccess?: () => void) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  /** Circuit breaker: once exhausted, cloud sync is disabled until a save succeeds. */
  const circuitOpenRef = useRef(false);
  const onSaveSuccessRef = useRef(onSaveSuccess);
  onSaveSuccessRef.current = onSaveSuccess;

  const setAutosaveStatus = useStore((s) => s.setAutosaveStatus);
  const setUnsavedChanges = useStore((s) => s.setUnsavedChanges);

  /** Generate a concise chat title from the first user message */
  const generateTitle = useCallback((messages: ChatMessage[]): string => {
    const firstUserMsg = messages.find((m) => m.role === 'user');
    if (!firstUserMsg) return 'New Chat';

    // Strip file attachment prefix if present
    let text = firstUserMsg.content.replace(/^\[Attached file:.*?\]\n\n[\s\S]*?\n\n/m, '').trim();
    if (!text) return 'File Analysis';

    // Remove markdown formatting, URLs, code blocks
    text = text
      .replace(/```[\s\S]*?```/g, '')       // code blocks
      .replace(/`[^`]+`/g, '')              // inline code
      .replace(/https?:\/\/\S+/g, '')       // URLs
      .replace(/[#*_~>\[\]()]/g, '')        // markdown chars
      .replace(/\s+/g, ' ')                 // collapse whitespace
      .trim();

    if (!text) return 'New Chat';

    // If it's a short question/request (under 50 chars), use it as-is
    if (text.length <= 50) {
      // Remove trailing punctuation for a cleaner title
      return text.replace(/[?.!,;:]+$/, '').trim() || 'New Chat';
    }

    // Extract a concise title: take the first sentence or clause
    const sentenceEnd = text.search(/[.?!]\s/);
    const clauseEnd = text.search(/[,;:\-–—]\s/);
    const newlineEnd = text.indexOf('\n');

    // Pick the shortest meaningful boundary
    const candidates = [sentenceEnd, clauseEnd, newlineEnd].filter((i) => i > 0 && i <= 80);
    const cutoff = candidates.length > 0 ? Math.min(...candidates) : -1;

    let title: string;
    if (cutoff > 0) {
      title = text.substring(0, cutoff).trim();
    } else {
      // No natural boundary — take first ~6 words
      const words = text.split(/\s+/);
      title = words.slice(0, 6).join(' ');
    }

    // Clean up and cap at 60 chars
    title = title.replace(/[?.!,;:]+$/, '').trim();
    if (title.length > 60) {
      title = title.substring(0, 57) + '...';
    }

    return title || 'New Chat';
  }, []);

  /** Execute the actual save operation */
  const executeSave = useCallback(
    async (
      buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>
    ): Promise<boolean> => {
      const state = useStore.getState();
      const { currentChatId, isAuthenticated, chatHistory, principal } = state;

      if (!currentChatId || !isAuthenticated || chatHistory.length === 0) {
        return false;
      }

      const title = generateTitle(chatHistory);

      const chatData = {
        chatId: currentChatId,
        title,
        messages: chatHistory.map((m) => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp,
        })),
        metadata: {
          title,
          createdAt: chatHistory[0]?.timestamp ?? Date.now(),
          updatedAt: Date.now(),
          messageCount: chatHistory.length,
          appVersion: CONFIG.APP_VERSION,
        },
      };

      // Local-first: save to IndexedDB immediately
      if (principal) {
        await IndexedDBStorage.saveChat(
          currentChatId,
          {
            title: chatData.title,
            messages: chatHistory,
            metadata: chatData.metadata,
            principal,
          },
          principal
        );
      }

      // Cloud sync
      try {
        // Skip cloud sync when circuit breaker is open (previous retries exhausted)
        if (circuitOpenRef.current) {
          Logger.info('Autosave circuit breaker open — local save only');
          setAutosaveStatus('saved');
          setUnsavedChanges(false);
          setTimeout(() => setAutosaveStatus('idle'), 2000);
          return true;
        }

        setAutosaveStatus('saving');
        const headers = await buildAuthHeaders('/chat/autosave');
        if (!headers) throw new Error('Auth headers unavailable');

        const response = await fetch(`${CONFIG.API_URL}/chat/autosave`, {
          method: 'POST',
          headers,
          body: JSON.stringify(chatData),
        });

        if (!response.ok) {
          throw new Error(`Autosave failed: ${response.status}`);
        }

        // Mark synced in IndexedDB
        await IndexedDBStorage.markSynced(currentChatId);
        setAutosaveStatus('saved');
        setUnsavedChanges(false);
        retryCountRef.current = 0;
        circuitOpenRef.current = false; // Reset circuit breaker on success

        // Refresh sidebar after successful cloud sync
        onSaveSuccessRef.current?.();

        // Reset to idle after 2s
        setTimeout(() => setAutosaveStatus('idle'), 2000);
        return true;
      } catch (err) {
        Logger.error('Autosave cloud sync failed:', err);
        setAutosaveStatus('error');

        // Queue for later sync
        await IndexedDBStorage.queueForSync(currentChatId, chatData);

        // Retry with exponential backoff up to MAX_RETRIES, then open circuit breaker
        if (retryCountRef.current < MAX_RETRIES) {
          retryCountRef.current++;
          const delay = RETRY_BASE_MS * Math.pow(RETRY_BACKOFF, retryCountRef.current - 1);
          Logger.info(`Autosave retry ${retryCountRef.current}/${MAX_RETRIES} in ${delay}ms`);
          setTimeout(() => void executeSave(buildAuthHeaders), delay);
        } else {
          // Open circuit breaker — stop hammering the backend
          circuitOpenRef.current = true;
          Logger.warn(
            `Autosave circuit breaker opened after ${MAX_RETRIES} failures. ` +
            'Cloud sync disabled until next successful save or page reload.',
          );
          setAutosaveStatus('error');
        }

        return false;
      }
    },
    [generateTitle, setAutosaveStatus, setUnsavedChanges]
  );

  /** Schedule an autosave with debounce */
  const scheduleAutosave = useCallback(
    (buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>) => {
      const state = useStore.getState();
      if (!state.isAuthenticated || !state.currentChatId || state.chatHistory.length === 0) return;

      // Clear existing timer
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }

      timerRef.current = setTimeout(() => {
        void executeSave(buildAuthHeaders);
      }, DEBOUNCE_MS);
    },
    [executeSave]
  );

  /** Retry all pending sync items */
  const retryPendingSync = useCallback(
    async (
      buildAuthHeaders: (endpoint: string) => Promise<AuthHeaders | null>
    ) => {
      const pending = await IndexedDBStorage.getPendingSync();
      let synced = 0;
      let failed = 0;

      for (const item of pending) {
        if (item.attempts >= 10) {
          failed++;
          continue;
        }

        try {
          const headers = await buildAuthHeaders('/chat/autosave');
          if (!headers) continue;

          const response = await fetch(`${CONFIG.API_URL}/chat/autosave`, {
            method: 'POST',
            headers,
            body: JSON.stringify(item.data),
          });

          if (response.ok) {
            await IndexedDBStorage.markSynced(item.chatId);
            synced++;
          } else {
            failed++;
          }
        } catch {
          failed++;
        }
      }

      return { synced, failed };
    },
    []
  );

  return {
    scheduleAutosave,
    executeSave,
    retryPendingSync,
  };
}

export default useAutosave;
