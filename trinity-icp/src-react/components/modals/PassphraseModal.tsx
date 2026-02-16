/**
 * PassphraseModal — setup or unlock passphrase for encrypted memory.
 *
 * Shown after Ed25519 login:
 *   - First time: "Set a passphrase to protect your data"
 *   - Returning: "Enter passphrase to unlock your data"
 */
import { useState, useCallback } from 'react';
import styles from '../../styles/components/Modal.module.css';

interface PassphraseModalProps {
  mode: 'setup' | 'unlock';
  loading: boolean;
  error: string | null;
  onSetup: (passphrase: string) => Promise<boolean>;
  onUnlock: (passphrase: string) => Promise<boolean>;
  onSkip?: () => void;
}

export function PassphraseModal({
  mode,
  loading,
  error,
  onSetup,
  onUnlock,
  onSkip,
}: PassphraseModalProps) {
  const [passphrase, setPassphrase] = useState('');
  const [confirm, setConfirm] = useState('');
  const [localError, setLocalError] = useState('');

  const handleSetup = useCallback(async () => {
    if (passphrase.length < 8) {
      setLocalError('Passphrase must be at least 8 characters');
      return;
    }
    if (passphrase !== confirm) {
      setLocalError('Passphrases do not match');
      return;
    }
    setLocalError('');
    await onSetup(passphrase);
  }, [passphrase, confirm, onSetup]);

  const handleUnlock = useCallback(async () => {
    if (!passphrase) return;
    setLocalError('');
    await onUnlock(passphrase);
  }, [passphrase, onUnlock]);

  const displayError = localError || error;

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>
            {mode === 'setup' ? 'Protect Your Data' : 'Unlock Your Data'}
          </h2>
        </div>

        <div className={styles.body}>
          {mode === 'setup' && (
            <>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                Set a passphrase to encrypt your AI memory. Without it, no one can read your
                data — not even Trinity.
              </p>
              <input
                className={styles.input}
                type="password"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                placeholder="Enter passphrase (8+ characters)"
                autoFocus
                style={{ marginBottom: '8px' }}
              />
              <input
                className={styles.input}
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm passphrase"
                onKeyDown={(e) => e.key === 'Enter' && handleSetup()}
              />
              <div className={styles.footer} style={{ marginTop: '16px' }}>
                {onSkip && (
                  <button className={styles.secondaryBtn} onClick={onSkip}>
                    Skip for now
                  </button>
                )}
                <button
                  className={styles.primaryBtn}
                  onClick={handleSetup}
                  disabled={loading || passphrase.length < 8}
                >
                  {loading ? 'Setting up...' : 'Set Passphrase'}
                </button>
              </div>
            </>
          )}

          {mode === 'unlock' && (
            <>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                Enter your passphrase to decrypt your AI memory and chat history.
              </p>
              <input
                className={styles.input}
                type="password"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                placeholder="Enter passphrase"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handleUnlock()}
              />
              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button
                  className={styles.primaryBtn}
                  onClick={handleUnlock}
                  disabled={loading || !passphrase}
                >
                  {loading ? 'Unlocking...' : 'Unlock'}
                </button>
              </div>
            </>
          )}

          {displayError && (
            <p
              style={{
                color: 'var(--color-error)',
                marginTop: '8px',
                fontSize: '0.875rem',
              }}
            >
              {displayError}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default PassphraseModal;
