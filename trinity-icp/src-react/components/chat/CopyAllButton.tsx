/**
 * CopyAllButton — copy full message text.
 */
import { useState, useCallback } from 'react';
import { copyToClipboard } from '../../utils/codeParser';
import styles from '../../styles/components/Message.module.css';

interface CopyAllButtonProps {
  content: string;
}

export function CopyAllButton({ content }: CopyAllButtonProps) {
  const [label, setLabel] = useState('Copy all');

  const handleCopy = useCallback(async () => {
    const success = await copyToClipboard(content);
    if (success) {
      setLabel('Copied!');
      setTimeout(() => setLabel('Copy all'), 2000);
    }
  }, [content]);

  return (
    <button className={styles.actionBtn} onClick={handleCopy}>
      {label}
    </button>
  );
}

export default CopyAllButton;
