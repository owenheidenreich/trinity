/**
 * AuthModal — login / import key flow.
 */
import { useState, useCallback } from 'react';
import styles from '../../styles/components/Modal.module.css';

interface AuthModalProps {
  onLogin: () => Promise<{ success: boolean; privateKeyHex?: string }>;
  onImportKey: (key: string) => Promise<{ success: boolean }>;
  onClose?: () => void;
}

export function AuthModal({ onLogin, onImportKey, onClose }: AuthModalProps) {
  const [mode, setMode] = useState<'choice' | 'import' | 'showKey'>('choice');
  const [importKey, setImportKey] = useState('');
  const [generatedKey, setGeneratedKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = useCallback(async () => {
    setLoading(true);
    setError('');
    const result = await onLogin();
    setLoading(false);
    if (result.success && result.privateKeyHex) {
      setGeneratedKey(result.privateKeyHex);
      setMode('showKey');
    } else {
      setError('Login failed. Please try again.');
    }
  }, [onLogin]);

  const handleImport = useCallback(async () => {
    if (!importKey.trim()) return;
    setLoading(true);
    setError('');
    const result = await onImportKey(importKey.trim());
    setLoading(false);
    if (!result.success) {
      setError('Invalid key. Please check and try again.');
    }
  }, [importKey, onImportKey]);

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>
            {mode === 'choice' && 'Welcome to Trinity'}
            {mode === 'import' && 'Import Key'}
            {mode === 'showKey' && 'Save Your Key'}
          </h2>
          {onClose && (
            <button className={styles.closeBtn} onClick={onClose}>
              &times;
            </button>
          )}
        </div>

        <div className={styles.body}>
          {mode === 'choice' && (
            <>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                Trinity uses self-custody authentication. Your identity is an Ed25519 key pair stored
                only in your browser.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <button className={styles.primaryBtn} onClick={handleLogin} disabled={loading}>
                  {loading ? 'Generating...' : 'Create New Identity'}
                </button>
                <button className={styles.secondaryBtn} onClick={() => setMode('import')}>
                  Import Existing Key
                </button>
              </div>
            </>
          )}

          {mode === 'import' && (
            <>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '12px' }}>
                Paste your Ed25519 private key (hex format):
              </p>
              <input
                className={styles.input}
                value={importKey}
                onChange={(e) => setImportKey(e.target.value)}
                placeholder="Enter private key hex..."
                autoFocus
              />
              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button className={styles.secondaryBtn} onClick={() => setMode('choice')}>
                  Back
                </button>
                <button
                  className={styles.primaryBtn}
                  onClick={handleImport}
                  disabled={!importKey.trim() || loading}
                >
                  {loading ? 'Importing...' : 'Import'}
                </button>
              </div>
            </>
          )}

          {mode === 'showKey' && (
            <>
              <p className={styles.warning}>
                Save this key securely. It is the ONLY way to recover your identity. Trinity cannot
                recover it for you.
              </p>
              <div className={styles.keyDisplay}>{generatedKey}</div>
              <div className={styles.footer}>
                <button
                  className={styles.primaryBtn}
                  onClick={() => {
                    navigator.clipboard.writeText(generatedKey).catch(() => {});
                  }}
                >
                  Copy Key
                </button>
                <button className={styles.secondaryBtn} onClick={onClose}>
                  I've Saved It
                </button>
              </div>
            </>
          )}

          {error && <p style={{ color: 'var(--color-error)', marginTop: '8px', fontSize: '0.875rem' }}>{error}</p>}
        </div>
      </div>
    </div>
  );
}

export default AuthModal;
