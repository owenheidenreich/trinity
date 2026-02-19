import { useMemo, useState } from 'react';
import styles from '../../styles/components/MemoryPanel.module.css';

interface MemoryPanelProps {
  memoryData: unknown;
}

export function MemoryPanel({ memoryData }: MemoryPanelProps) {
  const [isOpen, setIsOpen] = useState(true);

  const rawJson = useMemo(() => {
    try {
      return JSON.stringify(memoryData ?? {}, null, 2);
    } catch {
      return String(memoryData ?? '');
    }
  }, [memoryData]);

  const factCount = useMemo(() => {
    const payload = memoryData as { facts?: Array<{ deleted?: boolean; invalid_at?: number | null }> } | null;
    if (!payload || !Array.isArray(payload.facts)) return 0;
    return payload.facts.filter((f) => !f.deleted && !f.invalid_at).length;
  }, [memoryData]);

  return (
    <div className={styles.memorySection}>
      <div className={styles.memoryHeader} onClick={() => setIsOpen((v) => !v)}>
        <span className={styles.memoryTitle}>
          <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`}>&#9654;</span>
          Memory (Raw) <span className={styles.memoryCount}>({factCount})</span>
        </span>
      </div>

      {isOpen && (
        <div className={styles.factList}>
          {!memoryData ? (
            <div className={styles.emptyState}>No memory loaded yet.</div>
          ) : (
            <pre className={styles.rawMemory}>{rawJson}</pre>
          )}
        </div>
      )}
    </div>
  );
}

export default MemoryPanel;
