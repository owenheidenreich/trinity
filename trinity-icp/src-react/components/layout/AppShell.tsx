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
import { Sidebar } from '../sidebar/Sidebar';
import { MessageList } from '../chat/MessageList';
import { MessageInput } from '../chat/MessageInput';
import { EmptyState } from './EmptyState';
import { AuthModal } from '../modals/AuthModal';
import { ConfirmModal } from '../modals/ConfirmModal';
import { KeyExportModal } from '../modals/KeyExportModal';
import { toastManager } from '../notifications/ToastProvider';
import CONFIG from '../../config';
import Logger from '../../utils/logger';
import styles from '../../styles/components/AppShell.module.css';

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [showKeyExport, setShowKeyExport] = useState(false);

  // Store
  const chatHistory = useStore((s) => s.chatHistory);
  const chatStarted = useStore((s) => s.chatStarted);
  const currentChatId = useStore((s) => s.currentChatId);
  const allChats = useStore((s) => s.allChats);
  const isGenerating = useStore((s) => s.isGenerating);
  const addMessage = useStore((s) => s.addMessage);
  const setAllChats = useStore((s) => s.setAllChats);
  const setChatHistory = useStore((s) => s.setChatHistory);
  const setCurrentChatId = useStore((s) => s.setCurrentChatId);
  const setChatStarted = useStore((s) => s.setChatStarted);
  const setContextMemory = useStore((s) => s.setContextMemory);
  const setUserMemory = useStore((s) => s.setUserMemory);
  const reset = useStore((s) => s.reset);

  // Hooks
  const auth = useAuth();
  const chat = useChat();
  const autosave = useAutosave();
  const { status: connectionStatus } = useConnection();

  // Load chat list and user memory on auth
  useEffect(() => {
    if (auth.isAuthenticated) {
      void loadChats();
      void loadUserMemory();
    }
  }, [auth.isAuthenticated]);

  const loadChats = useCallback(async () => {
    try {
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
    }
  }, [auth.buildAuthHeaders, setAllChats]);

  const loadUserMemory = useCallback(async () => {
    try {
      const headers = await auth.buildAuthHeaders('/user/memory');
      if (!headers) return;
      const response = await fetch(`${CONFIG.API_URL}/user/memory`, { headers });
      if (response.ok) {
        const data = await response.json();
        // Backend returns memory object directly (not wrapped in .memory)
        setUserMemory(data ?? null);
      }
    } catch (err) {
      Logger.error('Failed to load user memory:', err);
    }
  }, [auth.buildAuthHeaders, setUserMemory]);

  // Send message
  const handleSend = useCallback(
    async (message: string, attachment?: File) => {
      // If a file is attached, prepend its content to the prompt
      let prompt = message;
      if (attachment) {
        try {
          const text = await attachment.text();
          prompt = `[Attached file: ${attachment.name}]\n\n${text}\n\n${message}`;
        } catch {
          Logger.warn('Failed to read attachment, sending without it');
        }
      }

      // Add user message to history
      addMessage('user', prompt);

      // Initialize chat ID if needed — generate BEFORE sending so useChat picks it up
      let activeChatId = currentChatId;
      if (!activeChatId) {
        activeChatId = useStore.getState().generateChatId();
        setCurrentChatId(activeChatId);
        // Flush to store synchronously so useChat reads the new ID
        useStore.setState({ currentChatId: activeChatId });
      }

      // Send to backend
      const result = await chat.send(prompt, auth.buildAuthHeaders);

      if (!result.success) {
        if (result.error && result.error !== 'Aborted') {
          toastManager.error(result.error);
        }
        return;
      }

      // Add AI response to history when streaming completes
      // Use getTokens() to avoid stale closure (chat.tokens captures pre-stream value)
      const finalTokens = chat.getTokens();
      if (finalTokens) {
        addMessage('assistant', finalTokens);
      }

      // Trigger autosave
      autosave.scheduleAutosave(auth.buildAuthHeaders);

      // Refresh chat list
      void loadChats();
    },
    [addMessage, currentChatId, setCurrentChatId, chat, auth.buildAuthHeaders, autosave, loadChats]
  );

  // Load a specific chat
  const handleLoadChat = useCallback(
    async (chatId: string) => {
      try {
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
      }
    },
    [auth.buildAuthHeaders, setChatHistory, setCurrentChatId, setChatStarted, setContextMemory]
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

  // Pin/unpin chat — POST to /chat/:id/pin (backend toggles internally)
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
      // Update last assistant message
      const lastIdx = chatHistory.length - 1;
      if (lastIdx >= 0 && chatHistory[lastIdx]?.role === 'assistant') {
        const updated = [...chatHistory];
        updated[lastIdx] = { ...updated[lastIdx]!, content: finalTokens };
        setChatHistory(updated);
      }
    }
    autosave.scheduleAutosave(auth.buildAuthHeaders);
  }, [chat, auth.buildAuthHeaders, chatHistory, setChatHistory, autosave]);

  // Show auth modal if not authenticated
  if (!auth.isAuthenticated) {
    return (
      <AuthModal
        onLogin={auth.login}
        onImportKey={auth.importKey}
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
            onNewChat={handleNewChat}
            onLoadChat={handleLoadChat}
            onDeleteChat={(chatId) => setDeleteTarget(chatId)}
            onPinChat={handlePinChat}
            onExportChat={handleExportChat}
            onExportKey={handleExportKey}
            onLogout={auth.logout}
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
    </div>
  );
}

export default AppShell;
