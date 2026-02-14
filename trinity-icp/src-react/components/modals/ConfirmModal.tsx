/**
 * ConfirmModal — generic confirmation dialog.
 */
import styles from '../../styles/components/Modal.module.css';

interface ConfirmModalProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  destructive?: boolean;
}

export function ConfirmModal({
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  destructive,
}: ConfirmModalProps) {
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button className={styles.closeBtn} onClick={onCancel}>
            &times;
          </button>
        </div>
        <div className={styles.body}>
          <p style={{ color: 'var(--color-text-secondary)' }}>{message}</p>
        </div>
        <div className={styles.footer}>
          <button className={styles.secondaryBtn} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            className={styles.primaryBtn}
            onClick={onConfirm}
            style={destructive ? { background: 'var(--color-error)' } : undefined}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmModal;
