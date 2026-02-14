/**
 * Message — single message wrapper (user or AI).
 */
import { useCallback } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { CopyAllButton } from './CopyAllButton';
import styles from '../../styles/components/Message.module.css';

interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  onEdit?: (content: string) => void;
}

export function Message({ role, content, onEdit }: MessageProps) {
  const handleEdit = useCallback(() => {
    onEdit?.(content);
  }, [content, onEdit]);

  return (
    <div className={`${styles.message} ${role === 'user' ? styles.user : styles.assistant}`}>
      <MarkdownRenderer content={content} className={styles.content} />
      <div className={styles.actions}>
        {role === 'assistant' && <CopyAllButton content={content} />}
        {role === 'user' && onEdit && (
          <button className={styles.actionBtn} onClick={handleEdit}>
            Edit
          </button>
        )}
      </div>
    </div>
  );
}

export default Message;
