/**
 * EmptyState — shown when no chat is active.
 */
import styles from '../../styles/components/EmptyState.module.css';

export function EmptyState() {
  return (
    <div className={styles.container}>
      <div className={styles.logo}>&#9651;</div>
      <h2 className={styles.title}>Trinity AI</h2>
      <p className={styles.subtitle}>
        Start a conversation by typing a message below. Your chats are encrypted and stored with
        self-custody authentication.
      </p>
    </div>
  );
}

export default EmptyState;
