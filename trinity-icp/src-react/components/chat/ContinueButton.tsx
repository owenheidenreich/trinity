/**
 * ContinueButton — shown when response was truncated (done_reason === 'length').
 */
import styles from '../../styles/components/Message.module.css';

interface ContinueButtonProps {
  onContinue: () => void;
  disabled?: boolean;
}

export function ContinueButton({ onContinue, disabled }: ContinueButtonProps) {
  return (
    <button
      className={styles.actionBtn}
      onClick={onContinue}
      disabled={disabled}
      style={{
        opacity: 1,
        marginTop: '12px',
        padding: '8px 16px',
        fontSize: '0.875rem',
      }}
    >
      Continue generating...
    </button>
  );
}

export default ContinueButton;
