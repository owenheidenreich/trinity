/**
 * KeyExportModal — displays principal + private key with copy & security warnings.
 * Triggered from the sidebar "Export Key" button.
 */
import { useState, useCallback, useRef } from 'react';
import styles from '../../styles/components/Modal.module.css';

interface KeyExportModalProps {
  principal: string;
  privateKeyHex: string;
  onClose: () => void;
}

export function KeyExportModal({ principal, privateKeyHex, onClose }: KeyExportModalProps) {
  const [copied, setCopied] = useState(false);
  const keyRef = useRef<HTMLTextAreaElement>(null);

  const handleCopy = useCallback(async () => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(privateKeyHex);
      } else {
        keyRef.current?.select();
        document.execCommand('copy');
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      keyRef.current?.focus();
      keyRef.current?.select();
    }
  }, [privateKeyHex]);

  const handleConfirmClose = useCallback(() => {
    const confirmed = window.confirm(
      'Are you sure you have saved your private key securely? You will NOT be able to recover your identity without it.\n\nClick OK to close.\nClick Cancel to keep it open.'
    );
    if (confirmed) onClose();
  }, [onClose]);

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && handleConfirmClose()}>
      <div className={styles.modal} style={{ maxWidth: 600, border: '2px solid var(--color-accent)' }}>
        <div className={styles.header}>
          <span className={styles.title}>Your Trinity Identity</span>
        </div>

        <div className={styles.body}>
          {/* Principal */}
          <p className={styles.warning} style={{ color: 'var(--color-accent)', fontWeight: 600 }}>
            Principal ID (Authentication)
          </p>
          <div className={styles.keyDisplay}>{principal}</div>

          {/* Private Key */}
          <p className={styles.warning} style={{ fontWeight: 600 }}>
            Private Key (SAVE THIS SECURELY)
          </p>
          <textarea
            ref={keyRef}
            readOnly
            value={privateKeyHex}
            className={styles.input}
            style={{
              minHeight: 70,
              resize: 'none',
              lineHeight: 1.6,
            }}
          />
          <button
            className={styles.primaryBtn}
            onClick={handleCopy}
            style={{
              width: '100%',
              marginTop: 'var(--space-sm)',
              background: copied ? '#4CAF50' : 'var(--color-warning, #ff9800)',
              color: '#000',
              fontWeight: 600,
            }}
          >
            {copied ? 'Copied!' : 'Copy Private Key'}
          </button>

          {/* Security Warning */}
          <div
            style={{
              background: '#ff5252',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-md)',
              marginTop: 'var(--space-lg)',
            }}
          >
            <p style={{ color: '#fff', fontSize: '0.8125rem', lineHeight: 1.6, margin: 0 }}>
              <strong>CRITICAL SECURITY WARNING:</strong>
              <br /><br />
              This key controls your Trinity identity, chats, and future payment account.
              <br />Store it in a password manager or encrypted file.
              <br />Anyone with this key can access your account.
              <br />If you lose it, your chats and account are <strong>permanently lost</strong>.
              <br />Trinity does not store this key — you are responsible for it.
            </p>
          </div>
        </div>

        <div className={styles.footer}>
          <button
            className={styles.primaryBtn}
            onClick={handleConfirmClose}
            style={{
              width: '100%',
              background: 'linear-gradient(135deg, #4CAF50 0%, #45a049 100%)',
            }}
          >
            I Have Saved My Key Securely
          </button>
        </div>
      </div>
    </div>
  );
}

export default KeyExportModal;
