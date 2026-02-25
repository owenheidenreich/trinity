/**
 * Sidebar — collapsible sidebar with chat list, status, and identity management.
 * Uses @tanstack/react-virtual for virtualized rendering and tier-grouped display.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
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
  isGuest?: boolean;
  onNewChat: () => void;
  onLoadChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  onPinChat?: (chatId: string) => void;
  onExportChat?: (chatId: string) => void;
  onExportKey?: () => void;
  onLogout: () => void;
  onSignIn?: () => void;
  onShowInfo?: (variant: InfoVariant) => void;
}

const MAX_CHATS = 20;
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

export function Sidebar({
  chats,
  currentChatId,
  connectionStatus,
  isLoadingChats,
  isBusy,
  memoryData,
  isGuest,
  onNewChat,
  onLoadChat,
  onDeleteChat,
  onPinChat,
  onExportChat,
  onExportKey,
  onLogout,
  onSignIn,
  onShowInfo,
}: SidebarProps) {
  const [archivedExpanded, setArchivedExpanded] = useState(false);

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

  // Split into Recent / Archived tiers
  const { recentChats, archivedChats } = useMemo(() => {
    const now = Date.now();
    const recent: ChatListItem[] = [];
    const archived: ChatListItem[] = [];
    for (const c of sortedChats) {
      const isRecent =
        c.pinned ||
        (!c.archived && Number(c.lastUpdated ?? 0) > now - SEVEN_DAYS_MS);
      if (isRecent) {
        recent.push(c);
      } else {
        archived.push(c);
      }
    }
    return { recentChats: recent, archivedChats: archived };
  }, [sortedChats]);

  // Build a flat virtual list: [recent items] + optional [archived header + archived items]
  type VirtualRow =
    | { type: 'chat'; chat: ChatListItem }
    | { type: 'header'; label: string; count: number };

  const rows = useMemo<VirtualRow[]>(() => {
    const result: VirtualRow[] = recentChats.map((c) => ({
      type: 'chat' as const,
      chat: c,
    }));
    if (archivedChats.length > 0) {
      result.push({
        type: 'header' as const,
        label: 'Archived',
        count: archivedChats.length,
      });
      if (archivedExpanded) {
        for (const c of archivedChats) {
          result.push({ type: 'chat' as const, chat: c });
        }
      }
    }
    return result;
  }, [recentChats, archivedChats, archivedExpanded]);

  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) => (rows[index]?.type === 'header' ? 32 : 56),
    overscan: 5,
  });

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

      <div className={styles.chatList} ref={parentRef}>
        {isGuest ? (
          <div style={{
            padding: '20px 16px',
            color: 'var(--color-text-muted)',
            fontSize: '0.875rem',
            lineHeight: 1.5,
            textAlign: 'center',
          }}>
            <p style={{ marginBottom: '12px' }}>Sign in to save your chat history and unlock memory features.</p>
            {onSignIn && (
              <button
                onClick={onSignIn}
                style={{
                  background: 'var(--color-accent)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 20px',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 500,
                }}
              >
                Sign In / Create Account
              </button>
            )}
          </div>
        ) : (
          <>
        {isLoadingChats && (
          <div className={styles.loadingBar}>
            <div className={styles.loadingBarFill} />
          </div>
        )}
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const row = rows[virtualRow.index];
            if (!row) return null;

            if (row.type === 'header') {
              return (
                <div
                  key="archived-header"
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <button
                    className={styles.sectionHeader}
                    onClick={() => setArchivedExpanded((prev) => !prev)}
                  >
                    <span>{archivedExpanded ? '\u25BC' : '\u25B6'}</span>
                    <span>Archived ({row.count})</span>
                  </button>
                </div>
              );
            }

            return (
              <div
                key={row.chat.chatId}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <ChatItem
                  chat={row.chat}
                  isActive={row.chat.chatId === currentChatId}
                  disabled={!!isBusy}
                  onLoad={onLoadChat}
                  onDelete={onDeleteChat}
                  onPin={onPinChat}
                  onExport={onExportChat}
                />
              </div>
            );
          })}
        </div>
        {!isLoadingChats && chats.length === 0 && (
          <div style={{ padding: '16px', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            No chats yet
          </div>
        )}
          </>
        )}
      </div>

      {!isGuest && (
        <MemoryPanel
          memoryData={memoryData}
        />
      )}

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
          {isGuest ? 'Guest mode' : `${chats.length}/${MAX_CHATS} chats`}
        </div>

        <div className={styles.statusActions}>
          {isGuest ? (
            onSignIn && (
              <button className={styles.chatActionBtn} onClick={onSignIn}>
                Sign In
              </button>
            )
          ) : (
            <>
              {onExportKey && (
                <button className={styles.chatActionBtn} onClick={onExportKey}>
                  Export Key
                </button>
              )}
              <button className={styles.chatActionBtn} onClick={onLogout}>
                Logout
              </button>
            </>
          )}
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
