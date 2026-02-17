/**
 * AppShell — top-level layout component.
 * Composes sidebar + main chat area + modals.
 */
import { useState, useCallback, useEffect } from 'react';
import { useStore } from '../../store';
import { useAuth } from '../../hooks/useAuth';
import { useChat } from '../../hooks/useChat';
import { useAutosave } from '../../hooks/useAutosave';
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
import { AutosaveIndicator } from '../notifications/AutosaveIndicator';
import CONFIG from '../../config';
import Logger from '../../utils/logger';
import styles from '../../styles/components/AppShell.module.css';

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [showKeyExport, setShowKeyExport] = useState(false);
  const [infoVariant, setInfoVariant] = useState<InfoVariant | null>(null);
  const [isLoadingChats, setIsLoadingChats] = useState(false);

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
  const updateMemoryFact = useStore((s) => s.updateMemoryFact);
  const deleteMemoryFact = useStore((s) => s.deleteMemoryFact);
  const reset = useStore((s) => s.reset);

  // Hooks
  const auth = useAuth();
  const chat = useChat();
  const { status: connectionStatus } = useConnection();
  const passphrase = usePassphrase();

  const loadChats = useCallback(async () => {
    try {
      setIsLoadingChats(true);
      const headers = await auth.buildAuthHeaders('/chat/list');
      if (!headers) return;
      const response = await fetch(`${CONFIG.API_URL}/chat/list`, {
        headers,
      });
      if (response.ok) {
        const data = await response.json();
        setAllChats(data.chats ?? []);
      }
    } catch (err) {
      Logger.error('Failed to load chats:', err);
    } finally {
      setIsLoadingChats(false);
    }
  }, [auth.buildAuthHeaders, setAllChats]);

  const autosave = useAutosave(loadChats);

  // Auto-setup/unlock passphrase after authentication
  useEffect(() => {
    if (auth.isAuthenticated && passphrase.status !== 'unlocked') {
      const password = auth.getPassword();
      if (password) {
        void passphrase.setupOrUnlock(password, auth.buildAuthHeaders);
      }
    }
  }, [auth.isAuthenticated]);

  // Load chat list and user memory once passphrase is unlocked
  useEffect(() => {
    if (auth.isAuthenticated && passphrase.status === 'unlocked') {
      void loadChats();
      void loadUserMemory();
    }
  }, [auth.isAuthenticated, passphrase.status]);

  const loadUserMemory = useCallback(async () => {
    try {
      const headers = await auth.buildAuthHeaders('/user/memory');
      if (!headers) return;
      const response = await fetch(`${CONFIG.API_URL}/user/memory`, { headers });
      if (response.ok) {
        const data = await response.json();
        setUserMemory(data ?? null);
      }
    } catch (err) {
      Logger.error('Failed to load user memory:', err);
    }
  }, [auth.buildAuthHeaders, setUserMemory]);

  // Edit a memory fact via backend PUT, then optimistic local update
  const handleEditMemory = useCallback(
    async (index: number, updates: { text?: string; category?: string; importance?: number }) => {
      try {
        const headers = await auth.buildAuthHeaders(`/user/memory/fact/${index}`);
        if (!headers) return;
        const response = await fetch(`${CONFIG.API_URL}/user/memory/fact/${index}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify(updates),
        });
        if (response.ok) {
          updateMemoryFact(index, updates);
        } else {
          toastManager.error('Failed to update memory');
        }
      } catch (err) {
        Logger.error('Failed to edit memory fact:', err);
        toastManager.error('Failed to update memory');
      }
    },
    [auth.buildAuthHeaders, updateMemoryFact]
  );

  // Delete a memory fact via backend DELETE, then optimistic local update
  const handleDeleteMemory = useCallback(
    async (index: number) => {
      try {
        const headers = await auth.buildAuthHeaders(`/user/memory/fact/${index}`);
        if (!headers) return;
        const response = await fetch(`${CONFIG.API_URL}/user/memory/fact/${index}`, {
          method: 'DELETE',
          headers,
        });
        if (response.ok) {
          deleteMemoryFact(index);
        } else {
          toastManager.error('Failed to delete memory');
        }
      } catch (err) {
        Logger.error('Failed to delete memory fact:', err);
        toastManager.error('Failed to delete memory');
      }
    },
    [auth.buildAuthHeaders, deleteMemoryFact]
  );

  // Download memory as JSON
  const handleDownloadMemory = useCallback(() => {
    const mem = useStore.getState().userMemory;
    if (!mem) return;
    const activeFacts = mem.facts.filter(
      (f) => !f.deleted && !f.invalid_at
    );
    const blob = new Blob(
      [JSON.stringify({ facts: activeFacts, preferences: mem.preferences }, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'trinity-memories.json';
    a.click();
    URL.revokeObjectURL(url);
    toastManager.success('Memories downloaded');
  }, []);

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

      addMessage('user', prompt);

      const { currentChatId: latestChatId, generateChatId } = useStore.getState();
      let activeChatId = latestChatId;
      if (!activeChatId) {
        activeChatId = generateChatId();
        setCurrentChatId(activeChatId);
      }

      const result = await chat.send(prompt, auth.buildAuthHeaders);

      if (!result.success) {
        if (result.error && result.error !== 'Aborted') {
          toastManager.error(result.error);
        }
        const partialTokens = chat.getTokens();
        if (partialTokens) {
          addMessage('assistant', partialTokens);
          autosave.scheduleAutosave(auth.buildAuthHeaders);
        }
        return;
      }

      const finalTokens = chat.getTokens();
      if (finalTokens) {
        addMessage('assistant', finalTokens);
      } else {
        addMessage('assistant', '*The model processed your request but returned an empty response. Please try again — sometimes rephrasing helps.*');
      }

      autosave.scheduleAutosave(auth.buildAuthHeaders);
      // Refresh memory panel after backend background extraction completes (~2-3s)
      setTimeout(() => void loadUserMemory(), 3000);
    },
    [addMessage, setCurrentChatId, chat, auth.buildAuthHeaders, autosave, loadUserMemory]
  );

  // Load a specific chat
  const handleLoadChat = useCallback(
    async (chatId: string) => {
      try {
        setLoadingChat(true);
        const headers = await auth.buildAuthHeaders(`/chat/${chatId}`);
        if (!headers) return;
        const response = await fetch(`${CONFIG.API_URL}/chat/${chatId}`, {
          headers,
        });
        if (response.ok) {
          const data = await response.json();
          setChatHistory(data.messages ?? []);
          setCurrentChatId(chatId);
          setChatStarted(true);
          setContextMemory(
            (data.messages ?? []).slice(-useStore.getState().CONTEXT_WINDOW_SIZE)
          );
        }
      } catch (err) {
        Logger.error('Failed to load chat:', err);
      } finally {
        setLoadingChat(false);
      }
    },
    [auth.buildAuthHeaders, setChatHistory, setCurrentChatId, setChatStarted, setContextMemory, setLoadingChat]
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
    reset();
  }, [reset]);

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

      addMessage('user', content);
      const editResult = await chat.send(content, auth.buildAuthHeaders);

      if (!editResult.success) {
        if (editResult.error && editResult.error !== 'Aborted') {
          toastManager.error(editResult.error);
        }
        return;
      }

      const finalTokens = chat.getTokens();
      if (finalTokens) {
        addMessage('assistant', finalTokens);
      }

      autosave.scheduleAutosave(auth.buildAuthHeaders);
    },
    [chatHistory, setChatHistory, setContextMemory, addMessage, chat, auth.buildAuthHeaders, autosave]
  );

  // Continue generation
  const handleContinue = useCallback(async () => {
    await chat.continueGeneration(auth.buildAuthHeaders);
    const finalTokens = chat.getTokens();
    if (finalTokens) {
      const currentHistory = useStore.getState().chatHistory;
      const lastIdx = currentHistory.length - 1;
      if (lastIdx >= 0 && currentHistory[lastIdx]?.role === 'assistant') {
        const updated = [...currentHistory];
        updated[lastIdx] = { ...updated[lastIdx]!, content: finalTokens };
        setChatHistory(updated);
      }
    }
    autosave.scheduleAutosave(auth.buildAuthHeaders);
  }, [chat, auth.buildAuthHeaders, setChatHistory, autosave]);

  // Show welcome modal if not authenticated or passphrase not unlocked
  const needsAuth =
    auth.isInitializing ||
    !auth.isAuthenticated ||
    passphrase.status !== 'unlocked';

  if (needsAuth) {
    return (
      <WelcomeModal
        isInitializing={auth.isInitializing || (auth.isAuthenticated && passphrase.status !== 'unlocked')}
        savedUsername={auth.savedUsername}
        onRegister={handleRegister}
        onSignIn={handleSignIn}
      />
    );
  }

  return (
    <div className={styles.container}>
      {/* Sidebar */}
      {sidebarOpen && (
        <div className={styles.sidebar}>
          <Sidebar
            chats={allChats}
            currentChatId={currentChatId}
            connectionStatus={connectionStatus}
            isLoadingChats={isLoadingChats}
            memoryFacts={userMemory?.facts ?? []}
            onNewChat={handleNewChat}
            onLoadChat={handleLoadChat}
            onDeleteChat={(chatId) => setDeleteTarget(chatId)}
            onPinChat={handlePinChat}
            onExportChat={handleExportChat}
            onExportKey={handleExportKey}
            onLogout={auth.logout}
            onShowInfo={setInfoVariant}
            onEditMemory={handleEditMemory}
            onDeleteMemory={handleDeleteMemory}
            onDownloadMemory={handleDownloadMemory}
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
            agentResponse={chat.agentResponse}
            onEdit={handleEdit}
            onContinue={handleContinue}
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

      {/* Autosave indicator */}
      <AutosaveIndicator />
    </div>
  );
}

export default AppShell;
