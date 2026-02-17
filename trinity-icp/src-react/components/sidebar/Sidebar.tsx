/**
 * Sidebar — collapsible sidebar with chat list, status, and identity management.
 */
import { useCallback, useMemo } from 'react';
import type { ChatListItem, MemoryFact } from '../../types';
import type { ConnectionStatus } from '../../hooks/useConnection';
import type { InfoVariant } from '../modals/InfoModal';
import { MemoryPanel } from './MemoryPanel';
import styles from '../../styles/components/Sidebar.module.css';

interface SidebarProps {
  chats: ChatListItem[];
  currentChatId: string | null;
  connectionStatus: ConnectionStatus;
  isLoadingChats?: boolean;
  memoryFacts: MemoryFact[];
  onNewChat: () => void;
  onLoadChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  onPinChat?: (chatId: string) => void;
  onExportChat?: (chatId: string) => void;
  onExportKey?: () => void;
  onLogout: () => void;
  onShowInfo?: (variant: InfoVariant) => void;
  onEditMemory: (index: number, updates: { text?: string; category?: string; importance?: number }) => void;
  onDeleteMemory: (index: number) => void;
  onDownloadMemory: () => void;
}

const MAX_CHATS = 20;

export function Sidebar({
  chats,
  currentChatId,
  connectionStatus,
  isLoadingChats,
  memoryFacts,
  onNewChat,
  onLoadChat,
  onDeleteChat,
  onPinChat,
  onExportChat,
  onExportKey,
  onLogout,
  onShowInfo,
  onEditMemory,
  onDeleteMemory,
  onDownloadMemory,
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
          <button className={styles.newChatBtn} onClick={onNewChat}>
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
        facts={memoryFacts}
        onEdit={onEditMemory}
        onDelete={onDeleteMemory}
        onDownload={onDownloadMemory}
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
