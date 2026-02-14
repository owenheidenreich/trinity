/**
 * Sidebar — collapsible sidebar with chat list, status, and identity management.
 */
import { useCallback, useMemo } from 'react';
import type { ChatListItem } from '../../types';
import type { ConnectionStatus } from '../../hooks/useConnection';
import styles from '../../styles/components/Sidebar.module.css';

interface SidebarProps {
  chats: ChatListItem[];
  currentChatId: string | null;
  connectionStatus: ConnectionStatus;
  onNewChat: () => void;
  onLoadChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  onPinChat?: (chatId: string) => void;
  onExportChat?: (chatId: string) => void;
  onExportKey?: () => void;
  onLogout: () => void;
}

const MAX_CHATS = 20;

export function Sidebar({
  chats,
  currentChatId,
  connectionStatus,
  onNewChat,
  onLoadChat,
  onDeleteChat,
  onPinChat,
  onExportChat,
  onExportKey,
  onLogout,
}: SidebarProps) {
  // Sort: pinned first, then by lastUpdated descending
  const sortedChats = useMemo(() => {
    return [...chats].sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return (b.lastUpdated || 0) - (a.lastUpdated || 0);
    });
  }, [chats]);

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <span className={styles.title}>Trinity</span>
        <button className={styles.newChatBtn} onClick={onNewChat}>
          New Chat
        </button>
      </div>

      <div className={styles.chatList}>
        {sortedChats.map((chat) => (
          <ChatItem
            key={chat.chatId}
            chat={chat}
            isActive={chat.chatId === currentChatId}
            onLoad={onLoadChat}
            onDelete={onDeleteChat}
            onPin={onPinChat}
            onExport={onExportChat}
          />
        ))}
        {chats.length === 0 && (
          <div style={{ padding: '16px', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            No chats yet
          </div>
        )}
      </div>

      <div className={styles.statusPanel}>
        <div className={styles.statusRow}>
          <span
            className={`${styles.statusDot} ${
              connectionStatus.connected ? styles.connected : styles.disconnected
            }`}
          />
          <span>
            {connectionStatus.connected
              ? `Connected${connectionStatus.model ? ` — ${connectionStatus.model}` : ''}`
              : 'Disconnected'}
          </span>
        </div>

        <div className={styles.chatCount}>
          {chats.length}/{MAX_CHATS} chats
        </div>

        <div className={styles.statusActions}>
          {onExportKey && (
            <button className={styles.chatActionBtn} onClick={onExportKey}>
              Export Key
            </button>
          )}
          <button className={styles.chatActionBtn} onClick={onLogout}>
            Logout
          </button>
        </div>
      </div>
    </div>
  );
}

function formatDate(timestamp: number): string {
  if (!timestamp) return '';
  // Backend stores timestamps in milliseconds — no need to multiply
  return new Date(timestamp).toLocaleDateString();
}

function ChatItem({
  chat,
  isActive,
  onLoad,
  onDelete,
  onPin,
  onExport,
}: {
  chat: ChatListItem;
  isActive: boolean;
  onLoad: (chatId: string) => void;
  onDelete: (chatId: string) => void;
  onPin?: (chatId: string) => void;
  onExport?: (chatId: string) => void;
}) {
  const handleLoad = useCallback(() => onLoad(chat.chatId), [chat.chatId, onLoad]);
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onDelete(chat.chatId);
    },
    [chat.chatId, onDelete]
  );
  const handlePin = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onPin?.(chat.chatId);
    },
    [chat.chatId, onPin]
  );
  const handleExport = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onExport?.(chat.chatId);
    },
    [chat.chatId, onExport]
  );

  return (
    <div
      className={`${styles.chatItem} ${isActive ? styles.chatItemActive : ''} ${chat.pinned ? styles.chatItemPinned : ''}`}
      onClick={handleLoad}
    >
      <div className={styles.chatMeta}>
        <span className={styles.chatTitle}>
          {chat.pinned && <span className={styles.pinIcon}>*</span>}
          {chat.title || 'Untitled'}
        </span>
        {chat.lastUpdated > 0 && (
          <span className={styles.chatDate}>{formatDate(chat.lastUpdated)}</span>
        )}
      </div>
      <div className={styles.chatActions}>
        {onPin && (
          <button
            className={styles.chatActionBtn}
            onClick={handlePin}
            title={chat.pinned ? 'Unpin chat' : 'Pin chat'}
          >
            {chat.pinned ? '*' : '-'}
          </button>
        )}
        {onExport && (
          <button
            className={styles.chatActionBtn}
            onClick={handleExport}
            title="Export as Markdown"
          >
            &#8595;
          </button>
        )}
        <button
          className={`${styles.chatActionBtn} ${styles.deleteBtn}`}
          onClick={handleDelete}
          title="Delete chat"
        >
          &times;
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
