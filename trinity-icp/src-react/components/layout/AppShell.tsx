/**
 * AppShell — top-level layout component.
 * Composes sidebar + main chat area + modals.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useStore } from '../../store';
import { useAuth } from '../../hooks/useAuth';
import { useChat } from '../../hooks/useChat';
import { useConnection } from '../../hooks/useConnection';
import { usePassphrase } from '../../hooks/usePassphrase';
import { Sidebar } from '../sidebar/Sidebar';
import { MessageList } from '../chat/MessageList';
import { MessageInput } from '../chat/MessageInput';
import { EmptyState } from './EmptyState';
import { WelcomeModal } from '../modals/WelcomeModal';
import { ConfirmModal } from '../modals/ConfirmModal';
import { KeyExportModal } from '../modals/KeyExportModal';
import { InfoModal } from '../modals/InfoModal';
import type { InfoVariant } from '../modals/InfoModal';
import { toastManager } from '../notifications/ToastProvider';
import CONFIG from '../../config';
import Logger from '../../utils/logger';
import styles from '../../styles/components/AppShell.module.css';
import type { ChatListItem } from '../../types';

function normalizeChatItem(raw: Partial<ChatListItem> | null | undefined): ChatListItem | null {
  if (!raw?.chatId) return null;
  return {
    chatId: String(raw.chatId),
    title: String(raw.title ?? 'New Chat'),
    messageCount: Number(raw.messageCount ?? 0),
    createdAt: Number(raw.createdAt ?? 0),
    lastUpdated: Number(raw.lastUpdated ?? raw.createdAt ?? 0),
    pinned: Boolean(raw.pinned),
    archived: Boolean(raw.archived),
    isArchived: Boolean(raw.isArchived ?? raw.archived),
    cid: raw.cid,
  };
}

function normalizeChatList(raw: unknown): ChatListItem[] {
  if (!Array.isArray(raw)) return [];
  const deduped = new Map<string, ChatListItem>();
  for (const item of raw) {
    const normalized = normalizeChatItem(item as Partial<ChatListItem>);
    if (!normalized) continue;
    const existing = deduped.get(normalized.chatId);
    if (!existing) {
      deduped.set(normalized.chatId, normalized);
      continue;
    }
    const existingUpdated = Number(existing.lastUpdated ?? 0);
    const nextUpdated = Number(normalized.lastUpdated ?? 0);
    if (nextUpdated >= existingUpdated) {
      deduped.set(normalized.chatId, normalized);
    }
  }
  return Array.from(deduped.values());
}

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [showKeyExport, setShowKeyExport] = useState(false);
  const [infoVariant, setInfoVariant] = useState<InfoVariant | null>(null);
  const [isLoadingChats, setIsLoadingChats] = useState(false);
  const [showSignUpModal, setShowSignUpModal] = useState(false);
  const chatListRequestSeq = useRef(0);
  const memoryPollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Store
  const chatHistory = useStore((s) => s.chatHistory);
  const chatStarted = useStore((s) => s.chatStarted);
  const currentChatId = useStore((s) => s.currentChatId);
  const allChats = useStore((s) => s.allChats);
  const isGenerating = useStore((s) => s.isGenerating);
  const isLoadingChat = useStore((s) => s.isLoadingChat);
  const setLoadingChat = useStore((s) => s.setLoadingChat);
  const addMessage = useStore((s) => s.addMessage);
  const setAllChats = useStore((s) => s.setAllChats);
  const setChatHistory = useStore((s) => s.setChatHistory);
  const setCurrentChatId = useStore((s) => s.setCurrentChatId);
  const setChatStarted = useStore((s) => s.setChatStarted);
  const setContextMemory = useStore((s) => s.setContextMemory);
  const setUserMemory = useStore((s) => s.setUserMemory);
  const userMemory = useStore((s) => s.userMemory);
  const reset = useStore((s) => s.reset);

  // Pagination
  const hasMoreMessages = useStore((s) => s.hasMoreMessages);
  const setHasMoreMessages = useStore((s) => s.setHasMoreMessages);
  const setOldestMessageId = useStore((s) => s.setOldestMessageId);
  const prependMessages = useStore((s) => s.prependMessages);

  // Hooks
  const auth = useAuth();
  const chat = useChat();
  const { status: connectionStatus } = useConnection();
  const passphrase = usePassphrase();

  // Anonymous access — guest mode (no account, ephemeral chats)
  const isAnonymous = !auth.isInitializing && !auth.isAuthenticated;

  /** Header builder that works for both authenticated and anonymous users. */
  const effectiveBuildAuthHeaders = useCallback(
    async (endpoint: string): Promise<Record<string, string> | null> => {
      if (auth.isAuthenticated) {
        return auth.buildAuthHeaders(endpoint);
      }
      return { 'Content-Type': 'application/json' };
    },
    [auth.isAuthenticated, auth.buildAuthHeaders]
  );

  const loadChats = useCallback(async () => {
    const requestSeq = ++chatListRequestSeq.current;
    try {
      setIsLoadingChats(true);
      const headers = await auth.buildAuthHeaders('/chat/list');
      if (!headers) return;
      const response = await fetch(`${CONFIG.API_URL}/chat/list`, {
        headers,
      });
      if (response.ok) {
        const data = await response.json();
        if (requestSeq !== chatListRequestSeq.current) {
          return;
        }
        setAllChats(normalizeChatList(data.chats));
      }
    } catch (err) {
      Logger.error('Failed to load chats:', err);
    } finally {
      if (requestSeq === chatListRequestSeq.current) {
        setIsLoadingChats(false);
      }
    }
  }, [auth.buildAuthHeaders, setAllChats]);

  const ensureCanonicalChatId = useCallback(async (): Promise<string | null> => {
    const existing = useStore.getState().currentChatId;
    if (existing) return existing;

    const headers = await effectiveBuildAuthHeaders('/chat/start');
    if (!headers) return null;

    const response = await fetch(`${CONFIG.API_URL}/chat/start`, {
      method: 'POST',
      headers,
      body: JSON.stringify({}),
    });
    if (!response.ok) return null;

    const data = await response.json();
    const chatId = data?.chat_id ? String(data.chat_id) : null;
    if (chatId) {
      setCurrentChatId(chatId);
    }
    return chatId;
  }, [effectiveBuildAuthHeaders, setCurrentChatId]);

  // Auto-setup/unlock passphrase after authentication
  useEffect(() => {
    if (auth.isAuthenticated && passphrase.status !== 'unlocked') {
      const password = auth.getPassword();
      if (password) {
        void passphrase.setupOrUnlock(password, auth.buildAuthHeaders);
      }
    }
  }, [auth.isAuthenticated]);

  const loadUserMemory = useCallback(async () => {
    try {
      const headers = await auth.buildAuthHeaders('/user/memory');
      if (!headers) return null;
      const response = await fetch(`${CONFIG.API_URL}/user/memory?raw=1`, { headers });
      if (response.ok) {
        const data = await response.json();
        setUserMemory(data ?? null);
        return data ?? null;
      }
    } catch (err) {
      Logger.error('Failed to load user memory:', err);
    }
    return null;
  }, [auth.buildAuthHeaders, setUserMemory]);

  // Load chat list and user memory once passphrase is unlocked
  useEffect(() => {
    if (auth.isAuthenticated && passphrase.status === 'unlocked') {
      void loadChats();
      void loadUserMemory();
    }
  }, [auth.isAuthenticated, passphrase.status, loadChats, loadUserMemory]);

  const refreshMemoryAfterIngestion = useCallback(() => {
    // Cancel any in-progress poll before starting a new one so rapid
    // sends don't accumulate overlapping setInterval loops.
    if (memoryPollTimerRef.current) {
      clearInterval(memoryPollTimerRef.current);
      memoryPollTimerRef.current = null;
    }

    let attempts = 0;
    const maxAttempts = 15;
    const minAttemptsBeforeStop = 3;

    const pollOnce = async () => {
      attempts += 1;
      const data = await loadUserMemory();
      const jobs = Array.isArray(data?.ingestion_jobs_recent) ? data.ingestion_jobs_recent : [];
      const hasPending = jobs.some((job: { status?: string }) => {
        const status = (job?.status ?? '').toLowerCase();
        return status === 'queued' || status === 'retry' || status === 'processing';
      });

      if ((attempts >= minAttemptsBeforeStop && !hasPending) || attempts >= maxAttempts) {
        if (memoryPollTimerRef.current) {
          clearInterval(memoryPollTimerRef.current);
          memoryPollTimerRef.current = null;
        }
      }
    };

    void pollOnce();
    memoryPollTimerRef.current = setInterval(() => {
      void pollOnce();
    }, 2000);
  }, [loadUserMemory]);

  const normalizeMessages = useCallback(
    (
      chatId: string,
      messages: Array<{
        id?: number;
        message_id?: number;
        role: 'user' | 'assistant';
        content: string;
        createdAt?: number;
        timestamp?: number;
      }>
    ) =>
      messages.map((m, idx) => {
        const createdAt = m.createdAt ?? m.timestamp ?? Date.now();
        const id = Number(m.id ?? m.message_id ?? -(createdAt + idx));
        return {
          id,
          chatId,
          role: m.role,
          content: m.content,
          createdAt,
          status: 'persisted' as const,
          timestamp: createdAt,
        };
      }),
    []
  );

  // Register handler
  const handleRegister = useCallback(
    async (username: string, password: string) => {
      return auth.register(username, password);
    },
    [auth.register]
  );

  // Sign-in handler
  const handleSignIn = useCallback(
    async (username: string, password: string) => {
      return auth.signIn(username, password);
    },
    [auth.signIn]
  );

  // Send message
  const handleSend = useCallback(
    async (message: string, attachment?: File) => {
      let prompt = message;
      if (attachment) {
        try {
          const text = await attachment.text();
          prompt = `[Attached file: ${attachment.name}]\n\n${text}\n\n${message}`;
        } catch {
          Logger.warn('Failed to read attachment, sending without it');
        }
      }

      const canonicalChatId = await ensureCanonicalChatId();
      if (!canonicalChatId) {
        toastManager.error('Failed to create chat session');
        return;
      }

      const pendingUserMessage = addMessage('user', prompt);
      const sendChatId = canonicalChatId || pendingUserMessage.chatId;
      // Start polling memory immediately so queued/processing ingestion jobs
      // become visible quickly in the raw memory panel (skip for anonymous).
      if (!isAnonymous) {
        refreshMemoryAfterIngestion();
      }

      const result = await chat.send(prompt, effectiveBuildAuthHeaders);

      if (!result.success) {
        if (result.error && result.error !== 'Aborted') {
          toastManager.error(result.error);
        }
        const partialTokens = chat.getTokens();
        if (partialTokens && useStore.getState().currentChatId === sendChatId) {
          addMessage('assistant', partialTokens);
        }
        return;
      }

      // For guest users: chats are ephemeral — just add the response locally.
      // For authenticated users: refresh from server to get persisted IDs.
      if (isAnonymous) {
        const finalTokens = chat.getTokens();
        if (finalTokens) {
          addMessage('assistant', finalTokens);
        } else {
          addMessage('assistant', '*The model processed your request but returned an empty response. Please try again.*');
        }
      } else {
        const persistedChatId = result.chatId ?? sendChatId;
        if (persistedChatId) {
          try {
            const headers = await effectiveBuildAuthHeaders(`/chat/${persistedChatId}`);
            if (headers) {
              const response = await fetch(`${CONFIG.API_URL}/chat/${persistedChatId}?limit=80`, {
                headers,
              });
              if (response.ok) {
                const data = await response.json();
                const normalizedMessages = normalizeMessages(persistedChatId, data.messages ?? []);
                if (useStore.getState().currentChatId === persistedChatId) {
                  setChatHistory(normalizedMessages);
                  setContextMemory(normalizedMessages.slice(-useStore.getState().CONTEXT_WINDOW_SIZE));
                  setChatStarted(normalizedMessages.length > 0);
                }
              } else {
                // Server fetch failed — fall back to local tokens
                const fallbackTokens = chat.getTokens();
                if (fallbackTokens) {
                  addMessage('assistant', fallbackTokens);
                }
              }
            }
          } catch (err) {
            Logger.error('Failed to refresh persisted chat after send:', err);
            // Fall back to local tokens on error
            const fallbackTokens = chat.getTokens();
            if (fallbackTokens) {
              addMessage('assistant', fallbackTokens);
            }
          }
        } else {
          const finalTokens = chat.getTokens();
          if (finalTokens) {
            addMessage('assistant', finalTokens);
          } else {
            addMessage('assistant', '*The model processed your request but returned an empty response. Please try again.*');
          }
        }
        void loadChats();
      }
    },
    [
      addMessage,
      chat,
      effectiveBuildAuthHeaders,
      normalizeMessages,
      setChatHistory,
      setContextMemory,
      setChatStarted,
      loadChats,
      refreshMemoryAfterIngestion,
      ensureCanonicalChatId,
      isAnonymous,
    ]
  );

  // Load a specific chat
  const handleLoadChat = useCallback(
    async (chatId: string) => {
      if (chat.isStreaming || isGenerating) {
        toastManager.error('Please wait for the current response to finish');
        return;
      }
      try {
        setLoadingChat(true);
        const headers = await auth.buildAuthHeaders(`/chat/${chatId}`);
        if (!headers) return;
        const response = await fetch(`${CONFIG.API_URL}/chat/${chatId}?limit=50`, {
          headers,
        });
        if (response.ok) {
          const data = await response.json();
          const normalizedMessages = normalizeMessages(chatId, data.messages ?? []);
          setChatHistory(normalizedMessages);
          setCurrentChatId(chatId);
          setChatStarted(normalizedMessages.length > 0);
          setContextMemory(
            normalizedMessages.slice(-useStore.getState().CONTEXT_WINDOW_SIZE)
          );
          setHasMoreMessages(data.pagination?.has_more ?? false);
          if (normalizedMessages.length > 0) {
            setOldestMessageId(normalizedMessages[0]!.id);
          } else {
            setOldestMessageId(null);
          }
        }
      } catch (err) {
        Logger.error('Failed to load chat:', err);
      } finally {
        setLoadingChat(false);
      }
    },
    [
      chat.isStreaming,
      isGenerating,
      auth.buildAuthHeaders,
      normalizeMessages,
      setChatHistory,
      setCurrentChatId,
      setChatStarted,
      setContextMemory,
      setLoadingChat,
      setHasMoreMessages,
      setOldestMessageId,
    ]
  );

  // Load earlier messages (pagination)
  const loadMoreMessages = useCallback(
    async () => {
      const state = useStore.getState();
      if (!state.currentChatId || !state.oldestMessageId || !state.hasMoreMessages) return;
      try {
        const headers = await auth.buildAuthHeaders(`/chat/${state.currentChatId}`);
        if (!headers) return;
        const response = await fetch(
          `${CONFIG.API_URL}/chat/${state.currentChatId}?limit=50&before_message_id=${state.oldestMessageId}`,
          { headers }
        );
        if (response.ok) {
          const data = await response.json();
          const normalized = normalizeMessages(state.currentChatId, data.messages ?? []);
          prependMessages(normalized);
          setHasMoreMessages(data.pagination?.has_more ?? false);
          if (normalized.length > 0) {
            setOldestMessageId(normalized[0]!.id);
          }
        }
      } catch (err) {
        Logger.error('Failed to load earlier messages:', err);
      }
    },
    [auth.buildAuthHeaders, normalizeMessages, prependMessages, setHasMoreMessages, setOldestMessageId]
  );

  // Delete chat
  const handleDeleteChat = useCallback(
    async (chatId: string) => {
      try {
        const headers = await auth.buildAuthHeaders(`/chat/${chatId}`);
        if (!headers) return;
        await fetch(`${CONFIG.API_URL}/chat/${chatId}`, {
          method: 'DELETE',
          headers,
        });
        void loadChats();
        if (chatId === currentChatId) {
          reset();
        }
      } catch (err) {
        Logger.error('Failed to delete chat:', err);
      }
      setDeleteTarget(null);
    },
    [auth.buildAuthHeaders, loadChats, currentChatId, reset]
  );

  // New chat
  const handleNewChat = useCallback(() => {
    if (chat.isStreaming || isGenerating) {
      toastManager.error('Please wait for the current response to finish');
      return;
    }
    void (async () => {
      try {
        const headers = await auth.buildAuthHeaders('/chat/start');
        if (!headers) return;
        const response = await fetch(`${CONFIG.API_URL}/chat/start`, {
          method: 'POST',
          headers,
          body: JSON.stringify({}),
        });
        const data = response.ok ? await response.json() : null;
        setChatHistory([]);
        setContextMemory([]);
        setChatStarted(false);
        setCurrentChatId(data?.chat_id ?? null);
        void loadChats();
      } catch (err) {
        Logger.error('Failed to start new chat:', err);
        reset();
      }
    })();
  }, [
    chat.isStreaming,
    isGenerating,
    auth.buildAuthHeaders,
    setChatHistory,
    setContextMemory,
    setChatStarted,
    setCurrentChatId,
    loadChats,
    reset,
  ]);

  // Pin/unpin chat
  const handlePinChat = useCallback(
    async (chatId: string) => {
      try {
        const headers = await auth.buildAuthHeaders(`/chat/${chatId}/pin`);
        if (!headers) return;
        await fetch(`${CONFIG.API_URL}/chat/${chatId}/pin`, {
          method: 'POST',
          headers,
        });
        void loadChats();
      } catch (err) {
        Logger.error('Failed to pin chat:', err);
        toastManager.error('Failed to pin chat');
      }
    },
    [auth.buildAuthHeaders, loadChats]
  );

  // Export chat as Markdown
  const handleExportChat = useCallback(
    async (chatId: string) => {
      try {
        const headers = await auth.buildAuthHeaders(`/chat/${chatId}`);
        if (!headers) return;
        const response = await fetch(`${CONFIG.API_URL}/chat/${chatId}`, { headers });
        if (!response.ok) throw new Error('Failed to load chat');
        const data = await response.json();
        const title = data.title || 'Untitled';
        const messages = data.messages ?? [];

        const lines = [`# ${title}\n`];
        for (const msg of messages) {
          const label = msg.role === 'user' ? '**You**' : '**Trinity**';
          lines.push(`### ${label}\n\n${msg.content}\n`);
        }

        const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title.replace(/[^a-zA-Z0-9-_ ]/g, '')}.md`;
        a.click();
        URL.revokeObjectURL(url);
        toastManager.success('Chat exported');
      } catch (err) {
        Logger.error('Failed to export chat:', err);
        toastManager.error('Failed to export chat');
      }
    },
    [auth.buildAuthHeaders]
  );

  // Key export
  const handleExportKey = useCallback(() => {
    const keys = auth.exportKey();
    if (keys.principal && keys.privateKeyHex) {
      setShowKeyExport(true);
    } else {
      toastManager.error('No key available');
    }
  }, [auth]);

  // Edit and regenerate
  const handleEdit = useCallback(
    async (messageIndex: number, content: string) => {
      const truncated = chatHistory.slice(0, messageIndex);
      setChatHistory(truncated);
      setContextMemory(
        truncated.slice(-useStore.getState().CONTEXT_WINDOW_SIZE)
      );

      const editChatId = await ensureCanonicalChatId();
      if (!editChatId) {
        toastManager.error('Failed to resolve chat for edit');
        return;
      }
      addMessage('user', content);
      if (!isAnonymous) {
        refreshMemoryAfterIngestion();
      }
      const editResult = await chat.send(content, effectiveBuildAuthHeaders);

      if (!editResult.success) {
        if (editResult.error && editResult.error !== 'Aborted') {
          toastManager.error(editResult.error);
        }
        return;
      }

      if (isAnonymous) {
        const finalTokens = chat.getTokens();
        if (finalTokens) {
          addMessage('assistant', finalTokens);
        }
      } else {
        const persistedChatId = editChatId;
        if (persistedChatId) {
          try {
            const headers = await effectiveBuildAuthHeaders(`/chat/${persistedChatId}`);
            if (headers) {
              const response = await fetch(`${CONFIG.API_URL}/chat/${persistedChatId}?limit=80`, {
                headers,
              });
              if (response.ok) {
                const data = await response.json();
                const normalizedMessages = normalizeMessages(persistedChatId, data.messages ?? []);
                if (useStore.getState().currentChatId === persistedChatId) {
                  setChatHistory(normalizedMessages);
                  setContextMemory(normalizedMessages.slice(-useStore.getState().CONTEXT_WINDOW_SIZE));
                  setChatStarted(normalizedMessages.length > 0);
                }
              } else {
                const fallbackTokens = chat.getTokens();
                if (fallbackTokens) addMessage('assistant', fallbackTokens);
              }
            }
          } catch (err) {
            Logger.error('Failed to refresh chat after edit:', err);
            const fallbackTokens = chat.getTokens();
            if (fallbackTokens) addMessage('assistant', fallbackTokens);
          }
        }
      }
    },
    [
      chatHistory,
      setChatHistory,
      setContextMemory,
      setChatStarted,
      addMessage,
      chat,
      effectiveBuildAuthHeaders,
      normalizeMessages,
      refreshMemoryAfterIngestion,
      ensureCanonicalChatId,
      isAnonymous,
    ]
  );

  // Clear sign-in modal when auth succeeds
  useEffect(() => {
    if (auth.isAuthenticated && passphrase.status === 'unlocked' && showSignUpModal) {
      setShowSignUpModal(false);
    }
  }, [auth.isAuthenticated, passphrase.status, showSignUpModal]);

  // Show welcome modal: initializing, passphrase locked, or user clicked sign in
  const showWelcomeModal =
    auth.isInitializing ||
    (auth.isAuthenticated && passphrase.status !== 'unlocked') ||
    showSignUpModal;

  if (showWelcomeModal) {
    return (
      <WelcomeModal
        isInitializing={auth.isInitializing || (auth.isAuthenticated && passphrase.status !== 'unlocked')}
        savedUsername={auth.savedUsername}
        onRegister={handleRegister}
        onSignIn={handleSignIn}
        onDismiss={
          // Allow dismiss if user voluntarily opened modal (not auto-restore / passphrase unlock)
          showSignUpModal && !auth.isInitializing && !(auth.isAuthenticated && passphrase.status !== 'unlocked')
            ? () => setShowSignUpModal(false)
            : undefined
        }
      />
    );
  }

  return (
    <div className={styles.container}>
      {/* Sidebar — always visible, adapts to guest/auth mode */}
      {sidebarOpen && (
        <div className={styles.sidebar}>
          <Sidebar
            chats={allChats}
            currentChatId={currentChatId}
            connectionStatus={connectionStatus}
            isLoadingChats={isLoadingChats}
            isBusy={chat.isStreaming || isLoadingChat || isGenerating}
            memoryData={userMemory}
            isGuest={isAnonymous}
            onNewChat={handleNewChat}
            onLoadChat={handleLoadChat}
            onDeleteChat={(chatId) => setDeleteTarget(chatId)}
            onPinChat={handlePinChat}
            onExportChat={handleExportChat}
            onExportKey={handleExportKey}
            onLogout={auth.logout}
            onSignIn={() => setShowSignUpModal(true)}
            onShowInfo={setInfoVariant}
          />
        </div>
      )}

      {/* Toggle sidebar button */}
      <button
        onClick={() => setSidebarOpen((prev) => !prev)}
        style={{
          position: 'absolute',
          top: '16px',
          left: sidebarOpen ? '296px' : '16px',
          background: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text-secondary)',
          width: '32px',
          height: '32px',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          zIndex: 10,
          transition: 'left var(--transition-normal)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {sidebarOpen ? '\u2190' : '\u2192'}
      </button>

      {/* Main content */}
      <div className={styles.main}>
        {isLoadingChat && (
          <div className={styles.loadingOverlay}>
            <div className={styles.spinner} />
            <span>Loading chat...</span>
          </div>
        )}
        {!chatStarted && !chat.isStreaming ? (
          <EmptyState />
        ) : (
          <MessageList
            messages={chatHistory}
            streamingTokens={chat.tokens}
            isStreaming={chat.isStreaming}
            phase={chat.phase}
            onEdit={handleEdit}
            hasMoreMessages={hasMoreMessages}
            onLoadMore={loadMoreMessages}
          />
        )}

        <div className={styles.inputArea}>
          <MessageInput
            onSend={handleSend}
            onStop={chat.stop}
            isGenerating={isGenerating}
            disabled={!connectionStatus.connected}
          />
        </div>
      </div>

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <ConfirmModal
          title="Delete Chat"
          message="Are you sure you want to delete this chat? This action cannot be undone."
          confirmLabel="Delete"
          destructive
          onConfirm={() => void handleDeleteChat(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Key export modal */}
      {showKeyExport && (() => {
        const keys = auth.exportKey();
        return keys.principal && keys.privateKeyHex ? (
          <KeyExportModal
            principal={keys.principal}
            privateKeyHex={keys.privateKeyHex}
            onClose={() => setShowKeyExport(false)}
          />
        ) : null;
      })()}

      {/* Info modal */}
      {infoVariant && (
        <InfoModal
          variant={infoVariant}
          data={{
            model: connectionStatus.model,
            gpu_type: connectionStatus.gpuType,
            provider: connectionStatus.provider,
          }}
          onClose={() => setInfoVariant(null)}
        />
      )}
    </div>
  );
}

export default AppShell;
