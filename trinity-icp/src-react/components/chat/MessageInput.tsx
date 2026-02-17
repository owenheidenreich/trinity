/**
 * MessageInput — textarea + send/stop + file attachment.
 */
import { useState, useCallback, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from 'react';
import styles from '../../styles/components/MessageInput.module.css';

interface MessageInputProps {
  onSend: (message: string, attachment?: File) => void;
  onStop: () => void;
  isGenerating: boolean;
  disabled?: boolean;
}

export function MessageInput({ onSend, onStop, isGenerating, disabled }: MessageInputProps) {
  const [value, setValue] = useState('');
  const [attachment, setAttachment] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wasGeneratingRef = useRef(false);

  // Auto-focus on mount (user just logged in) and when generation finishes
  useEffect(() => {
    if (!disabled && !isGenerating) {
      // Small delay so the DOM is settled after re-enable
      const id = setTimeout(() => textareaRef.current?.focus(), 50);
      return () => clearTimeout(id);
    }
  }, [disabled]); // on initial enable (login)

  useEffect(() => {
    // Detect transition from generating → not generating
    if (wasGeneratingRef.current && !isGenerating && !disabled) {
      const id = setTimeout(() => textareaRef.current?.focus(), 50);
      wasGeneratingRef.current = false;
      return () => clearTimeout(id);
    }
    wasGeneratingRef.current = isGenerating;
  }, [isGenerating, disabled]);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled || isGenerating) return;
    onSend(trimmed, attachment ?? undefined);
    setValue('');
    setAttachment(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [value, attachment, disabled, isGenerating, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (isGenerating) return;
        handleSend();
      }
    },
    [handleSend, isGenerating]
  );

  const handleChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const input = e.target.value;
    // Client-side length limit (50k chars)
    if (input.length > 50_000) return;
    setValue(input);
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, []);

  const handleFileSelect = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Client-side file size limit (10MB)
    if (file.size > 10 * 1024 * 1024) {
      // Could integrate with toast system for user feedback
      return;
    }
    setAttachment(file);
  }, []);

  const clearAttachment = useCallback(() => {
    setAttachment(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  return (
    <div>
      {attachment && (
        <div className={styles.filePreview}>
          <span>{attachment.name}</span>
          <button className={styles.filePreviewClose} onClick={clearAttachment}>
            &times;
          </button>
        </div>
      )}
      <div className={styles.container}>
        <button
          className={styles.attachBtn}
          onClick={() => fileInputRef.current?.click()}
          title="Attach file"
        >
          +
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.json,.pdf,.doc,.docx,.py,.js,.ts,.html,.css"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <div className={styles.textareaWrapper}>
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={isGenerating ? 'Waiting for response...' : 'Ask anything...'}
            rows={1}
            disabled={disabled || isGenerating}
          />
        </div>
        {isGenerating ? (
          <button className={`${styles.sendBtn} ${styles.stopBtn}`} onClick={onStop}>
            &#9632;
          </button>
        ) : (
          <button
            className={styles.sendBtn}
            onClick={handleSend}
            disabled={!value.trim() || disabled}
          >
            &#9650;
          </button>
        )}
      </div>
    </div>
  );
}

export default MessageInput;
