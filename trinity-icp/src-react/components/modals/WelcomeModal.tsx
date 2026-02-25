/**
 * WelcomeModal — username + password authentication.
 *
 * Two forms:
 *   Create Account: username + password + confirm → register on-chain
 *   Sign In:        username + password → verify on-chain
 *
 * Crypto details are hidden. No backup keys, no canary concepts.
 * The user's password deterministically derives their Ed25519 identity
 * via Argon2id — same credentials = same identity on any device.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import styles from '../../styles/components/Modal.module.css';
import { isUsernameAvailable } from '../../services/canister';

type Mode = 'signin' | 'create';

interface WelcomeModalProps {
  isInitializing: boolean;
  savedUsername: string | null;
  onRegister: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  onSignIn: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  onDismiss?: () => void;
}

export function WelcomeModal({
  isInitializing,
  savedUsername,
  onRegister,
  onSignIn,
  onDismiss,
}: WelcomeModalProps) {
  // Default to sign-in if we have a saved username (returning user)
  const [mode, setMode] = useState<Mode>(savedUsername ? 'signin' : 'create');
  const [username, setUsername] = useState(savedUsername ?? '');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');
  const [usernameAvailable, setUsernameAvailable] = useState<boolean | null>(null);
  const [usernameChecking, setUsernameChecking] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear error + fields when switching modes
  useEffect(() => {
    setError('');
    setPassword('');
    setConfirm('');
    setUsernameAvailable(null);
  }, [mode]);

  // Live username availability check (debounced)
  useEffect(() => {
    if (mode !== 'create' || username.length < 3) {
      setUsernameAvailable(null);
      return;
    }

    // Validate format locally first
    if (!/^[a-z0-9_]+$/i.test(username)) {
      setUsernameAvailable(null);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);

    setUsernameChecking(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const available = await isUsernameAvailable(username);
        setUsernameAvailable(available);
      } catch {
        setUsernameAvailable(null);
      } finally {
        setUsernameChecking(false);
      }
    }, 400);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [username, mode]);

  // Create Account
  const handleCreate = useCallback(async () => {
    if (username.length < 3) {
      setError('Username must be at least 3 characters');
      return;
    }
    if (!/^[a-z0-9_]+$/i.test(username)) {
      setError('Username may only contain letters, numbers, and underscores');
      return;
    }
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
    setLoadingText('Deriving identity...');

    // Small delay so the loading text renders before Argon2id blocks
    await new Promise((r) => setTimeout(r, 50));
    setLoadingText('Creating account...');

    const result = await onRegister(username, password);
    setLoading(false);
    setLoadingText('');

    if (!result.success) {
      setError(result.error || 'Registration failed');
    }
  }, [username, password, confirm, onRegister]);

  // Sign In
  const handleSignIn = useCallback(async () => {
    if (!username) {
      setError('Enter your username');
      return;
    }
    if (!password) {
      setError('Enter your password');
      return;
    }

    setError('');
    setLoading(true);
    setLoadingText('Deriving identity...');

    await new Promise((r) => setTimeout(r, 50));
    setLoadingText('Verifying...');

    const result = await onSignIn(username, password);
    setLoading(false);
    setLoadingText('');

    if (!result.success) {
      setError(result.error || 'Sign-in failed');
    }
  }, [username, password, onSignIn]);

  // Loading state
  if (isInitializing) {
    return (
      <div className={styles.overlay}>
        <div className={styles.modal}>
          <div className={styles.header}>
            <h2 className={styles.title}>Trinity</h2>
          </div>
          <div className={styles.body}>
            <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0' }}>
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
        </div>
      </div>
    );
  }

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        {/* ─── Create Account ─── */}
        {mode === 'create' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Create Account</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px', lineHeight: 1.5 }}>
                Your password creates your cryptographic identity.
                No email or phone required.
              </p>

              {/* Username */}
              <div style={{ position: 'relative', marginBottom: '8px' }}>
                <input
                  className={styles.input}
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                  placeholder="Username (3-20 chars, a-z 0-9 _)"
                  autoFocus
                  maxLength={20}
                  autoComplete="username"
                  disabled={loading}
                />
                {username.length >= 3 && (
                  <span style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    fontSize: '0.75rem',
                    color: usernameChecking
                      ? 'var(--color-text-secondary)'
                      : usernameAvailable === true
                        ? 'var(--color-success, #4ade80)'
                        : usernameAvailable === false
                          ? 'var(--color-error)'
                          : 'var(--color-text-secondary)',
                  }}>
                    {usernameChecking
                      ? '...'
                      : usernameAvailable === true
                        ? 'available'
                        : usernameAvailable === false
                          ? 'taken'
                          : ''}
                  </span>
                )}
              </div>

              {/* Password */}
              <input
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password (8+ characters)"
                autoComplete="new-password"
                disabled={loading}
                style={{ marginBottom: '8px' }}
              />

              {/* Confirm */}
              <input
                className={styles.input}
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm password"
                autoComplete="new-password"
                disabled={loading}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />

              {/* Warning */}
              <p style={{
                color: 'var(--color-text-secondary)',
                fontSize: '0.75rem',
                marginTop: '12px',
                lineHeight: 1.4,
                opacity: 0.7,
              }}>
                If you forget your password, your data cannot be recovered.
                Trinity does not collect personal information.
              </p>

              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button
                  className={styles.primaryBtn}
                  onClick={handleCreate}
                  disabled={loading || password.length < 8 || usernameAvailable === false}
                  style={{ width: '100%', padding: '12px' }}
                >
                  {loading ? loadingText || 'Creating...' : 'Create Account'}
                </button>
              </div>

              <p style={{
                textAlign: 'center',
                marginTop: '16px',
                fontSize: '0.8125rem',
                color: 'var(--color-text-secondary)',
              }}>
                Already have an account?{' '}
                <button
                  onClick={() => setMode('signin')}
                  disabled={loading}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-accent)',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    fontSize: 'inherit',
                    padding: 0,
                  }}
                >
                  Sign In
                </button>
              </p>
            </div>
          </>
        )}

        {/* ─── Sign In ─── */}
        {mode === 'signin' && (
          <>
            <div className={styles.header}>
              <h2 className={styles.title}>Welcome Back</h2>
            </div>
            <div className={styles.body}>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
                Sign in to access your encrypted data.
              </p>

              <input
                className={styles.input}
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                placeholder="Username"
                autoFocus={!savedUsername}
                autoComplete="username"
                disabled={loading}
                style={{ marginBottom: '8px' }}
              />
              <input
                className={styles.input}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoFocus={!!savedUsername}
                autoComplete="current-password"
                disabled={loading}
                onKeyDown={(e) => e.key === 'Enter' && handleSignIn()}
              />

              <div className={styles.footer} style={{ marginTop: '16px' }}>
                <button
                  className={styles.primaryBtn}
                  onClick={handleSignIn}
                  disabled={loading || !username || !password}
                  style={{ width: '100%', padding: '12px' }}
                >
                  {loading ? loadingText || 'Signing in...' : 'Sign In'}
                </button>
              </div>

              <p style={{
                textAlign: 'center',
                marginTop: '16px',
                fontSize: '0.8125rem',
                color: 'var(--color-text-secondary)',
              }}>
                New here?{' '}
                <button
                  onClick={() => setMode('create')}
                  disabled={loading}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-accent)',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    fontSize: 'inherit',
                    padding: 0,
                  }}
                >
                  Create Account
                </button>
              </p>
            </div>
          </>
        )}

        {/* ─── Error display ─── */}
        {error && (
          <p style={{
            color: 'var(--color-error)',
            margin: '0 24px 16px',
            fontSize: '0.875rem',
          }}>
            {error}
          </p>
        )}

        {/* ─── Dismiss (back to chat) ─── */}
        {onDismiss && (
          <div style={{ textAlign: 'center', padding: '0 24px 20px' }}>
            <button
              onClick={onDismiss}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-text-secondary)',
                cursor: 'pointer',
                fontSize: '0.8125rem',
                textDecoration: 'underline',
                padding: 0,
              }}
            >
              Continue without account
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default WelcomeModal;
