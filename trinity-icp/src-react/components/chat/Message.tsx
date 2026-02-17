/**
 * Message — single message wrapper (user or AI).
 * Supports: markdown rendering, code blocks, download cards, inline editing.
 */
import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { CopyAllButton } from './CopyAllButton';
import { DownloadCards } from './DownloadCards';
import type { DownloadFile } from './DownloadCards';
import { extractCodeBlocks } from '../../utils/codeParser';
import styles from '../../styles/components/Message.module.css';

interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  onEdit?: (content: string) => void;
}

/** Minimum lines for a code block to be offered as a download */
const MIN_DOWNLOAD_LINES = 3;

/**  Map extracted code blocks → DownloadFile[] */
function codeBlocksToFiles(content: string): DownloadFile[] {
  // Fast exit: no triple-backtick fences means no code blocks to scan
  if (!content.includes('```')) return [];

  const blocks = extractCodeBlocks(content);
  return blocks
    .filter((b) => {
      const trimmed = b.code.trim();
      // Skip empty blocks and tiny snippets (inline examples)
      return trimmed.length > 0 && trimmed.split('\n').length >= MIN_DOWNLOAD_LINES;
    })
    .map((b) => ({
      filename: b.filename || b.displayName,
      content: b.code,
    }));
}

export function Message({ role, content, onEdit }: MessageProps) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (editing && textareaRef.current) {
      const ta = textareaRef.current;
      ta.style.height = 'auto';
      ta.style.height = ta.scrollHeight + 'px';
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
  }, [editing]);

  const handleStartEdit = useCallback(() => {
    setEditText(content);
    setEditing(true);
  }, [content]);

  const handleCancelEdit = useCallback(() => {
    setEditing(false);
    setEditText(content);
  }, [content]);

  const handleSaveEdit = useCallback(() => {
    setEditing(false);
    if (editText.trim() && editText !== content) {
      onEdit?.(editText.trim());
    }
  }, [editText, content, onEdit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSaveEdit();
      } else if (e.key === 'Escape') {
        handleCancelEdit();
      }
    },
    [handleSaveEdit, handleCancelEdit]
  );

  // Extract downloadable files from assistant messages
  const downloadFiles = useMemo(
    () => (role === 'assistant' ? codeBlocksToFiles(content) : []),
    [role, content]
  );

  return (
    <div className={`${styles.message} ${role === 'user' ? styles.user : styles.assistant}`}>
      {editing ? (
        <div className={styles.editContainer}>
          <textarea
            ref={textareaRef}
            className={styles.editTextarea}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
          />
          <div className={styles.editActions}>
            <button className={styles.editCancelBtn} onClick={handleCancelEdit}>
              Cancel
            </button>
            <button className={styles.editSaveBtn} onClick={handleSaveEdit}>
              Save & Regenerate
            </button>
          </div>
        </div>
      ) : (
        <>
          <MarkdownRenderer content={content} className={styles.content} />
          {downloadFiles.length > 0 && <DownloadCards files={downloadFiles} />}
          <div className={styles.actions}>
            {role === 'assistant' && <CopyAllButton content={content} />}
            {role === 'user' && onEdit && (
              <button className={styles.actionBtn} onClick={handleStartEdit}>
                Edit
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default Message;
