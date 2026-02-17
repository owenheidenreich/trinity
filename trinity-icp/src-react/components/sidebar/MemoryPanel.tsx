/**
 * MemoryPanel — collapsible sidebar section showing user's stored memories.
 * Renders below the chat list, always visible. Supports inline edit and delete.
 */
import { useState, useCallback, useMemo } from 'react';
import type { MemoryFact } from '../../types';
import styles from '../../styles/components/MemoryPanel.module.css';

const CATEGORIES = ['identity', 'work', 'interests', 'preferences', 'relationships', 'general'] as const;

interface MemoryPanelProps {
  facts: MemoryFact[];
  onEdit: (index: number, updates: { text?: string; category?: string; importance?: number }) => void;
  onDelete: (index: number) => void;
  onDownload: () => void;
}

export function MemoryPanel({ facts, onEdit, onDelete, onDownload }: MemoryPanelProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  // Only show active (non-deleted, non-invalidated) facts
  const activeFacts = useMemo(() => {
    const indexed: { fact: MemoryFact; originalIndex: number }[] = [];
    facts.forEach((f, i) => {
      if (!f.deleted && !f.invalid_at) {
        indexed.push({ fact: f, originalIndex: i });
      }
    });
    return indexed;
  }, [facts]);

  const handleDownload = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onDownload();
  }, [onDownload]);

  return (
    <div className={styles.memorySection}>
      <div className={styles.memoryHeader} onClick={() => setIsOpen((v) => !v)}>
        <span className={styles.memoryTitle}>
          <span className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`}>&#9654;</span>
          Memory <span className={styles.memoryCount}>({activeFacts.length})</span>
        </span>
        <div className={styles.headerActions}>
          <button
            className={styles.iconBtn}
            onClick={handleDownload}
            title="Download memories as JSON"
          >
            &#8595;
          </button>
        </div>
      </div>

      {isOpen && (
        <div className={styles.factList}>
          {activeFacts.length === 0 ? (
            <div className={styles.emptyState}>
              No memories yet. As you chat, Trinity will learn about you.
            </div>
          ) : (
            activeFacts.map(({ fact, originalIndex }) =>
              editingIndex === originalIndex ? (
                <EditFactForm
                  key={originalIndex}
                  fact={fact}
                  onSave={(updates) => {
                    onEdit(originalIndex, updates);
                    setEditingIndex(null);
                  }}
                  onCancel={() => setEditingIndex(null)}
                />
              ) : (
                <FactItem
                  key={originalIndex}
                  fact={fact}
                  onEdit={() => setEditingIndex(originalIndex)}
                  onDelete={() => onDelete(originalIndex)}
                />
              )
            )
          )}
        </div>
      )}
    </div>
  );
}

// ── Individual fact display ──────────────────────────────────────────

function FactItem({
  fact,
  onEdit,
  onDelete,
}: {
  fact: MemoryFact;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const text = fact.text || fact.fact || '';
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onDelete();
    },
    [onDelete]
  );

  return (
    <div className={styles.factItem} onClick={onEdit} title="Click to edit">
      <span className={styles.factText}>{text}</span>
      <div className={styles.factMeta}>
        <span className={styles.categoryBadge} data-cat={fact.category}>
          {fact.category}
        </span>
        <button className={styles.deleteBtn} onClick={handleDelete} title="Delete">
          &times;
        </button>
      </div>
    </div>
  );
}

// ── Inline edit form ─────────────────────────────────────────────────

function EditFactForm({
  fact,
  onSave,
  onCancel,
}: {
  fact: MemoryFact;
  onSave: (updates: { text?: string; category?: string; importance?: number }) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(fact.text || fact.fact || '');
  const [category, setCategory] = useState(fact.category || 'general');
  const [importance, setImportance] = useState(fact.importance ?? 3);

  const handleSave = useCallback(() => {
    const updates: { text?: string; category?: string; importance?: number } = {};
    const originalText = fact.text || fact.fact || '';
    if (text !== originalText) updates.text = text;
    if (category !== fact.category) updates.category = category;
    if (importance !== (fact.importance ?? 3)) updates.importance = importance;

    if (Object.keys(updates).length > 0) {
      onSave(updates);
    } else {
      onCancel();
    }
  }, [text, category, importance, fact, onSave, onCancel]);

  return (
    <div className={styles.editForm}>
      <textarea
        className={styles.editTextarea}
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoFocus
      />
      <div className={styles.editRow}>
        <select
          className={styles.editSelect}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.charAt(0).toUpperCase() + c.slice(1)}
            </option>
          ))}
        </select>
        <div className={styles.importanceRow}>
          <span className={styles.importanceLabel}>Imp:</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <div
              key={n}
              className={`${styles.importanceDot} ${n <= importance ? styles.importanceDotActive : ''}`}
              onClick={() => setImportance(n)}
              title={`Importance ${n}`}
            />
          ))}
        </div>
      </div>
      <div className={styles.editActions}>
        <button className={styles.editBtn} onClick={onCancel}>
          Cancel
        </button>
        <button className={`${styles.editBtn} ${styles.editBtnPrimary}`} onClick={handleSave}>
          Save
        </button>
      </div>
    </div>
  );
}

export default MemoryPanel;
