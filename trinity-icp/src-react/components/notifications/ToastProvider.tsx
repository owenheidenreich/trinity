/**
 * ToastProvider — lightweight toast notification system.
 * Renders a stack of auto-dismissing notifications.
 *
 * Usage:
 *   <ToastProvider />   (rendered once in App.tsx)
 *   const toast = useToast();
 *   toast.success('Saved');
 *   toast.error('Something went wrong');
 *   toast.warning('Rate limited');
 *   toast.info('Connecting...');
 *   toast.rateLimitCountdown(30);
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import styles from '../../styles/components/Toast.module.css';

// ── Types ──────────────────────────────────────────────────────────────────

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  /** Auto-dismiss in ms (0 = sticky) */
  duration: number;
  /** Optional link */
  link?: { url: string; label: string };
  /** Countdown text (for rate-limit toasts) */
  countdown?: number;
}

type ToastListener = (toasts: ToastItem[]) => void;

// ── Singleton store (usable outside React) ─────────────────────────────────

let nextId = 1;
let toasts: ToastItem[] = [];
const listeners = new Set<ToastListener>();

function notify() {
  const snapshot = [...toasts];
  listeners.forEach((fn) => fn(snapshot));
}

function addToast(
  message: string,
  type: ToastType,
  opts: { duration?: number; link?: { url: string; label: string } } = {}
) {
  const id = nextId++;
  const duration = opts.duration ?? 3000;
  toasts = [...toasts, { id, message, type, duration, link: opts.link }];
  notify();

  if (duration > 0) {
    setTimeout(() => removeToast(id), duration);
  }
  return id;
}

function removeToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  notify();
}

/** Public API — importable from anywhere */
export const toastManager = {
  success(msg: string, opts?: { duration?: number; link?: { url: string; label: string } }) {
    return addToast(msg, 'success', opts);
  },
  error(msg: string, opts?: { duration?: number }) {
    return addToast(msg, 'error', { duration: 5000, ...opts });
  },
  warning(msg: string, opts?: { duration?: number }) {
    return addToast(msg, 'warning', opts);
  },
  info(msg: string, opts?: { duration?: number }) {
    return addToast(msg, 'info', opts);
  },
  /** Show a live countdown toast, auto-removes on finish. */
  rateLimitCountdown(seconds: number) {
    const id = nextId++;
    toasts = [...toasts, { id, message: '', type: 'warning', duration: 0, countdown: seconds }];
    notify();

    let remaining = seconds;
    const interval = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(interval);
        removeToast(id);
        addToast('Ready to continue!', 'success', { duration: 2000 });
        return;
      }
      toasts = toasts.map((t) =>
        t.id === id ? { ...t, countdown: remaining } : t
      );
      notify();
    }, 1000);
  },
  dismiss: removeToast,
};

// ── React hook ─────────────────────────────────────────────────────────────

export function useToast() {
  return toastManager;
}

// ── Provider component ─────────────────────────────────────────────────────

export function ToastProvider() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    listeners.add(setItems);
    return () => {
      listeners.delete(setItems);
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <div className={styles.container} role="status" aria-live="polite">
      {items.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={removeToast} />
      ))}
    </div>
  );
}

function Toast({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: (id: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  // Slide-in animation on mount
  useEffect(() => {
    requestAnimationFrame(() => {
      if (styles.show) ref.current?.classList.add(styles.show);
    });
  }, []);

  const handleDismiss = useCallback(() => {
    if (styles.show) ref.current?.classList.remove(styles.show);
    setTimeout(() => onDismiss(toast.id), 200);
  }, [toast.id, onDismiss]);

  const displayMessage =
    toast.countdown != null
      ? `Too many requests. Try again in ${toast.countdown}s`
      : toast.message;

  return (
    <div ref={ref} className={`${styles.toast} ${styles[toast.type]}`}>
      <span className={styles.message}>
        {displayMessage}
        {toast.link && (
          <>
            {' '}
            <a
              href={toast.link.url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.link}
            >
              {toast.link.label} &#8599;
            </a>
          </>
        )}
      </span>
      <button className={styles.dismiss} onClick={handleDismiss} aria-label="Dismiss">
        &times;
      </button>
    </div>
  );
}

export default ToastProvider;
