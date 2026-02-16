/**
 * WelcomeModal — unified auth + passphrase flow.
 *
 * Replaces the separate AuthModal → PassphraseModal chain with
 * a single component that guides users through the full flow:
 *
 *   New user:       Welcome → Set Password → (optional) Save Backup Key → Done
 *   Returning user: Welcome Back → Enter Password → Done
 *   Key restore:    Welcome → Restore Backup → Enter Password → Done
 *
 * Crypto details (Ed25519, hex keys) are hidden from normal users.
 * Backup key export is offered as an optional post-setup step.
 */
import { useState, useCallback, useEffect } from 'react';
import type { PassphraseStatus } from '../../hooks/usePassphrase';
import styles from '../../styles/components/Modal.module.css';

type Step =
  | 'loading'        // checking auth/passphrase status
  | 'welcome'        // not authenticated — "Get Started" / "Restore"
  | 'import'         // restoring from backup key
  | 'setup'          // set a password (new user, key just generated)
  | 'unlock'         // enter password (returning user)
  | 'backup'         // optional: save your backup key
  ;

interface WelcomeModalProps {
  isAuthenticated: boolean;
  isInitializing: boolean;
  passphraseStatus: PassphraseStatus;
  passphraseLoading: boolean;
  passphraseError: string | null;
  onCreateIdentity: () => Promise<{ success: boolean; privateKeyHex?: string }>;
  onImportKey: (key: string) => Promise<{ success: boolean }>;
  onSetupPassphrase: (passphrase: string) => Promise<boolean>;
  onUnlockPassphrase: (passphrase: string) => Promise<boolean>;
  onSkipPassphrase: () => void;
  onShowBackupKey: () => void;
  onDismissBackupKey: () => void;
}

export function WelcomeModal({
  isAuthenticated,
  isInitializing,
  passphraseStatus,
  passphraseLoading: _passphraseLoading,
  passphraseError,
  onCreateIdentity,
  onImportKey,
  onSetupPassphrase,
  onUnlockPassphrase,
  onSkipPassphrase,
  onShowBackupKey,
  onDismissBackupKey,
}: WelcomeModalProps) {
  const [step, setStep] = useState<Step>('loading');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [importKey, setImportKey] = useState('');
  const [backupKey, setBackupKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Derive step from auth + passphrase state
  useEffect(() => {
    if (isInitializing) {
      setStep('loading');
      return;
    }

    if (!isAuthenticated) {
      // Only move to welcome if we're not already in an active sub-step
      setStep((prev) => (prev === 'import' ? 'import' : 'welcome'));
      return;
    }

    // Authenticated — wait for passphrase status
    if (passphraseStatus === 'unknown') {
      setStep('loading');
      return;
    }

    if (passphraseStatus === 'no_passphrase') {
      // Don't override backup step
      setStep((prev) => (prev === 'backup' ? 'backup' : 'setup'));
      return;
    }

    if (passphraseStatus === 'locked') {
      setStep('unlock');
      return;
    }

    // 'unlocked' — modal should not render (handled by parent)
  }, [isAuthenticated, isInitializing, passphraseStatus]);

  // Clear errors when switching steps
  useEffect(() => {
    setError('');
    setPassword('');
    setConfirm('');
    setCopied(false);
  }, [step]);

  // "Get Started" — generate identity silently then move to password setup
  const handleGetStarted = useCallback(async () => {
    setLoading(true);
    setError('');
    const result = await onCreateIdentity();
    setLoading(false);
    if (result.success && result.privateKeyHex) {
      setBackupKey(result.privateKeyHex);
      // The useEffect will move us to 'setup' once passphrase check completes
    } else {
      setError('Something went wrong. Please try again.');
    }
  }, [onCreateIdentity]);

  // Import backup key
  const handleImport = useCallback(async () => {
    if (!importKey.trim()) return;
    setLoading(true);
    setError('');
    const result = await onImportKey(importKey.trim());
    setLoading(false);
    if (!result.success) {
      setError('Invalid backup key. Please check and try again.');
    }
    // Success → useEffect will transition to 'unlock' or 'setup'
  }, [importKey, onImportKey]);

  // Set password
  const handleSetup = useCallback(async () => {
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setError('');
    setLoading(true);
    const ok = await onSetupPassphrase(password);
    setLoading(false);
    if (ok) {
      // Only show backup step if we have a key to show (new user)
      if (backupKey) {
        onShowBackupKey();
        setStep('backup');
      }
      // Otherwise useEffect handles transition to unlocked → parent hides modal
    }
  }, [password, confirm, backupKey, onSetupPassphrase]);

  // Unlock with password
  const handleUnlock = useCallback(async () => {
    if (!password) return;
    setError('');
    setLoading(true);
    const ok = await onUnlockPassphrase(password);
    setLoading(false);
    if (!ok) {
      setError(passphraseError || 'Incorrect password. Please try again.');
    }
    // Success → useEffect handles transition
  }, [password, passphraseError, onUnlockPassphrase]);

  // Copy backup key
  const handleCopyKey = useCallback(() => {
    navigator.clipboard.writeText(backupKey).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [backupKey]);

  // Skip passphrase (for "Get Started" users who don't want a password)
  const handleSkip = useCallback(() => {
    onSkipPassphrase();
    if (backupKey) {
      onShowBackupKey();
      setStep('backup');
    }
  }, [backupKey, onSkipPassphrase, onShowBackupKey]);

  // Don't render if fully authenticated + unlocked (and not showing backup key)
  if (isAuthenticated && passphraseStatus === 'unlocked' && step !== 'backup') {
    return null;
  }

  const displayError = error || (passphraseError && step === 'unlock' ? passphraseError : '');

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        {/* ─── Loading ─── */}
        {step === 'loading' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Trinity</h2>
            </div>
            <div className={styles.body}>
              <div style={{
                display: 'flex',
                justifyContent: 'center',
                padding: '24px 0',
              }}>
                <div style={{
                  width: 28,
                  height: 28,
                  border: '3px solid var(--color-border)',
                  borderTopColor: 'var(--color-accent)',
                  borderRadius: '50%',
                  animation: 'spin 0.8s linear infinite',
                }} />
              </div>
            </div>
          </>
        )}

        {/* ─── Welcome (not authenticated) ─── */}
        {step === 'welcome' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Welcome to Trinity</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '24px', lineHeight: 1.5 }}>
                Your conversations are encrypted and stored with self-custody
                authentication. No email or account required.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button
                  className={styles.primaryBtn}
                  onClick={handleGetStarted}
                  disabled={loading}
                  style={{ padding: '12px 24px', fontSize: '1rem' }}
                >
                  {loading ? 'Setting up...' : 'Get Started'}
                </button>
                <button
                  className={styles.secondaryBtn}
                  onClick={() => setStep('import')}
                  style={{ fontSize: '0.8125rem' }}
                >
                  Restore from backup key
                </button>
              </div>
            </div>
          </>
        )}

        {/* ─── Import backup key ─── */}
        {step === 'import' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Restore Account</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '12px' }}>
                Paste the backup key you saved when you first created your account.
              </p>
              <textarea
                className={styles.input}
                value={importKey}
                onChange={(e) => setImportKey(e.target.value)}
                placeholder="Paste your backup key here..."
                autoFocus
                rows={3}
                style={{ resize: 'none' }}
              />
              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button className={styles.secondaryBtn} onClick={() => setStep('welcome')}>
                  Back
                </button>
                <button
                  className={styles.primaryBtn}
                  onClick={handleImport}
                  disabled={!importKey.trim() || loading}
                >
                  {loading ? 'Restoring...' : 'Restore'}
                </button>
              </div>
            </div>
          </>
        )}

        {/* ─── Setup password (new user) ─── */}
        {step === 'setup' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Set Your Password</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px', lineHeight: 1.5 }}>
                This password encrypts your AI memory and chat history. Without it,
                no one can read your data — not even Trinity.
              </p>
              <input
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password (8+ characters)"
                autoFocus
                style={{ marginBottom: '8px' }}
              />
              <input
                className={styles.input}
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm password"
                onKeyDown={(e) => e.key === 'Enter' && handleSetup()}
              />
              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button className={styles.secondaryBtn} onClick={handleSkip}>
                  Skip for now
                </button>
                <button
                  className={styles.primaryBtn}
                  onClick={handleSetup}
                  disabled={loading || password.length < 8}
                >
                  {loading ? 'Setting up...' : 'Continue'}
                </button>
              </div>
            </div>
          </>
        )}

        {/* ─── Unlock (returning user) ─── */}
        {step === 'unlock' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Welcome Back</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                Enter your password to unlock your data.
              </p>
              <input
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && handleUnlock()}
              />
              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button
                  className={styles.primaryBtn}
                  onClick={handleUnlock}
                  disabled={loading || !password}
                >
                  {loading ? 'Unlocking...' : 'Unlock'}
                </button>
              </div>
            </div>
          </>
        )}

        {/* ─── Save backup key (optional, after setup) ─── */}
        {step === 'backup' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Save Your Backup Key</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '8px', lineHeight: 1.5 }}>
                This key lets you restore your account on a new device or browser.
                Save it somewhere safe — Trinity cannot recover it for you.
              </p>
              <p className={styles.warning} style={{ marginBottom: '12px' }}>
                You can also export this later from the sidebar menu.
              </p>
              <div className={styles.keyDisplay}>{backupKey}</div>
              <div className={styles.footer}>
                <button className={styles.secondaryBtn} onClick={onDismissBackupKey}>
                  Skip
                </button>
                <button className={styles.primaryBtn} onClick={() => { handleCopyKey(); setTimeout(onDismissBackupKey, 1500); }}>
                  {copied ? 'Copied!' : 'Copy & Continue'}
                </button>
              </div>
            </div>
          </>
        )}

        {/* ─── Error display ─── */}
        {displayError && (
          <p style={{
            color: 'var(--color-error)',
            margin: '0 24px 16px',
            fontSize: '0.875rem',
          }}>
            {displayError}
          </p>
        )}
      </div>
    </div>
  );
}

export default WelcomeModal;
