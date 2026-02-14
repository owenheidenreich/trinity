/**
 * AutosaveIndicator — visual badge showing save status.
 * Shows "Saving..." (rainbow), "Saved" (green), or "Error" (red).
 * Matches the old vanilla JS autosave indicator behavior.
 */
import { useEffect, useState } from 'react';
import { useStore } from '../../store';
import styles from '../../styles/components/AutosaveIndicator.module.css';

export function AutosaveIndicator() {
  const autosaveStatus = useStore((s) => s.autosaveStatus);
  const [visible, setVisible] = useState(false);
  const [fadingOut, setFadingOut] = useState(false);

  useEffect(() => {
    if (autosaveStatus === 'saving') {
      setVisible(true);
      setFadingOut(false);
    } else if (autosaveStatus === 'saved') {
      setVisible(true);
      setFadingOut(false);
      // Fade out after 2s
      const timer = setTimeout(() => {
        setFadingOut(true);
        setTimeout(() => setVisible(false), 300);
      }, 2000);
      return () => clearTimeout(timer);
    } else if (autosaveStatus === 'error') {
      setVisible(true);
      setFadingOut(false);
      // Fade out after 4s
      const timer = setTimeout(() => {
        setFadingOut(true);
        setTimeout(() => setVisible(false), 300);
      }, 4000);
      return () => clearTimeout(timer);
    } else {
      // idle
      if (visible) {
        setFadingOut(true);
        const timer = setTimeout(() => setVisible(false), 300);
        return () => clearTimeout(timer);
      }
    }
  }, [autosaveStatus]);

  if (!visible) return null;

  const statusClass =
    autosaveStatus === 'saving'
      ? styles.saving
      : autosaveStatus === 'saved'
        ? styles.saved
        : autosaveStatus === 'error'
          ? styles.error
          : styles.saved;

  const label =
    autosaveStatus === 'saving'
      ? 'Saving...'
      : autosaveStatus === 'saved'
        ? 'Saved'
        : autosaveStatus === 'error'
          ? 'Save error'
          : '';

  return (
    <div className={styles.container}>
      <div className={`${styles.badge} ${statusClass} ${fadingOut ? styles.fadeOut : ''}`}>
        <span className={styles.dot} />
        {label}
      </div>
    </div>
  );
}

export default AutosaveIndicator;
