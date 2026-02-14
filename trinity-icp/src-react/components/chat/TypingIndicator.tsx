/**
 * TypingIndicator — phase-aware thinking animation.
 * Shows bouncing dots + optional phase badge during agent processing.
 */
import type { AgentPhase } from '../../types';
import styles from '../../styles/components/TypingIndicator.module.css';

interface TypingIndicatorProps {
  phase?: AgentPhase | null;
}

export function TypingIndicator({ phase }: TypingIndicatorProps) {
  return (
    <div className={styles.container}>
      <div className={styles.dots}>
        <span className={styles.dot} />
        <span className={styles.dot} />
        <span className={styles.dot} />
      </div>
      {phase && (
        <span className={styles.phase}>
          {phase.message || phase.name}
        </span>
      )}
    </div>
  );
}

export default TypingIndicator;
