/**
 * Sidebar — collapsible sidebar with chat list, status, and identity management.
 */
import { useCallback, useMemo } from 'react';
import type { ChatListItem } from '../../types';
import type { ConnectionStatus } from '../../hooks/useConnection';
import type { InfoVariant } from '../modals/InfoModal';
import { MemoryPanel } from './MemoryPanel';
import styles from '../../styles/components/Sidebar.module.css';

interface SidebarProps {
  chats: ChatListItem[];
  currentChatId: string | null;
  connectionStatus: ConnectionStatus;
  isLoadingChats?: boolean;
  isBusy?: boolean;
  memoryData: unknown;
  onNewChat: () => void;
  onLoadChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  onPinChat?: (chatId: string) => void;
  onExportChat?: (chatId: string) => void;
  onExportKey?: () => void;
  onLogout: () => void;
  onShowInfo?: (variant: InfoVariant) => void;
}

const MAX_CHATS = 20;

export function Sidebar({
  chats,
  currentChatId,
  connectionStatus,
  isLoadingChats,
  isBusy,
  memoryData,
  onNewChat,
  onLoadChat,
  onDeleteChat,
  onPinChat,
  onExportChat,
  onExportKey,
  onLogout,
  onShowInfo,
}: SidebarProps) {
  // Sort: pinned first, then by lastUpdated descending
  const sortedChats = useMemo(() => {
    return [...chats].sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      const aUpdated = Number(a.lastUpdated ?? a.createdAt ?? 0);
      const bUpdated = Number(b.lastUpdated ?? b.createdAt ?? 0);
      if (bUpdated !== aUpdated) return bUpdated - aUpdated;
      const aCreated = Number(a.createdAt ?? 0);
      const bCreated = Number(b.createdAt ?? 0);
      if (bCreated !== aCreated) return bCreated - aCreated;
      return String(b.chatId).localeCompare(String(a.chatId));
    });
  }, [chats]);

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <span className={styles.title}>Trinity</span>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {onShowInfo && (
            <button
              className={styles.chatActionBtn}
              onClick={() => onShowInfo('about')}
              title="About Trinity"
              style={{ fontSize: '0.75rem' }}
            >
              About
            </button>
          )}
          <button className={styles.newChatBtn} onClick={onNewChat} disabled={isBusy}>
            New Chat
          </button>
        </div>
      </div>

      <div className={styles.chatList}>
        {isLoadingChats && (
          <div className={styles.loadingBar}>
            <div className={styles.loadingBarFill} />
          </div>
        )}
        {sortedChats.map((chat) => (
          <ChatItem
            key={chat.chatId}
            chat={chat}
            isActive={chat.chatId === currentChatId}
            disabled={!!isBusy}
            onLoad={onLoadChat}
            onDelete={onDeleteChat}
            onPin={onPinChat}
            onExport={onExportChat}
          />
        ))}
        {!isLoadingChats && chats.length === 0 && (
          <div style={{ padding: '16px', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            No chats yet
          </div>
        )}
      </div>

      <MemoryPanel
        memoryData={memoryData}
      />

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

        {/* Infrastructure badges */}
        {connectionStatus.connected && onShowInfo && (
          <div style={{
            display: 'flex',
            gap: '6px',
            padding: '4px 0',
            flexWrap: 'wrap',
          }}>
            <button
              className={styles.chatActionBtn}
              onClick={() => onShowInfo('icp')}
              title="Internet Computer"
              style={{ fontSize: '0.7rem', padding: '2px 6px' }}
            >
              <span style={{ color: '#69db7c', fontSize: '8px', marginRight: '3px' }}>●</span>ICP
            </button>
            <button
              className={styles.chatActionBtn}
              onClick={() => onShowInfo('akash')}
              title="Akash Network"
              style={{ fontSize: '0.7rem', padding: '2px 6px' }}
            >
              <span style={{ color: connectionStatus.connected ? '#69db7c' : '#ff6b6b', fontSize: '8px', marginRight: '3px' }}>{connectionStatus.connected ? '●' : '○'}</span>Akash
            </button>
            <button
              className={styles.chatActionBtn}
              onClick={() => onShowInfo('ipfs')}
              title="IPFS Storage"
              style={{ fontSize: '0.7rem', padding: '2px 6px' }}
            >
              <span style={{ color: '#888', fontSize: '8px', marginRight: '3px' }}>●</span>IPFS
            </button>
            <button
              className={styles.chatActionBtn}
              onClick={() => onShowInfo('model')}
              title="AI Model"
              style={{ fontSize: '0.7rem', padding: '2px 6px' }}
            >
              <span style={{ color: connectionStatus.connected ? '#a78bfa' : '#888', fontSize: '8px', marginRight: '3px' }}>{connectionStatus.connected ? '●' : '○'}</span>Model
            </button>
          </div>
        )}

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
  disabled,
  onLoad,
  onDelete,
  onPin,
  onExport,
}: {
  chat: ChatListItem;
  isActive: boolean;
  disabled: boolean;
  onLoad: (chatId: string) => void;
  onDelete: (chatId: string) => void;
  onPin?: (chatId: string) => void;
  onExport?: (chatId: string) => void;
}) {
  const handleLoad = useCallback(() => {
    if (disabled) return;
    onLoad(chat.chatId);
  }, [disabled, chat.chatId, onLoad]);
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (disabled) return;
      onDelete(chat.chatId);
    },
    [disabled, chat.chatId, onDelete]
  );
  const handlePin = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (disabled) return;
      onPin?.(chat.chatId);
    },
    [disabled, chat.chatId, onPin]
  );
  const handleExport = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (disabled) return;
      onExport?.(chat.chatId);
    },
    [disabled, chat.chatId, onExport]
  );

  return (
    <div
      className={`${styles.chatItem} ${isActive ? styles.chatItemActive : ''} ${chat.pinned ? styles.chatItemPinned : ''}`}
      onClick={handleLoad}
      style={disabled ? { opacity: 0.7, cursor: 'not-allowed' } : undefined}
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
