/**
 * TypingIndicator — phase-aware thinking animation with whimsical messages.
 * Shows bouncing dots + rotating fun messages during agent processing.
 */
import { useState, useEffect, useRef } from 'react';
import type { AgentPhase } from '../../types';
import styles from '../../styles/components/TypingIndicator.module.css';

const LOADING_PHRASES: Record<string, [string, string][]> = {
  searching: [
    ['Scouring', 'web'],
    ['Exploring', 'internet'],
    ['Hunting', 'sources'],
    ['Mining', 'data'],
    ['Consulting', 'oracles'],
    ['Diving into', 'archives'],
    ['Querying', 'databases'],
    ['Surfing', 'information waves'],
  ],
  executing: [
    ['Brewing', 'answer'],
    ['Crafting', 'response'],
    ['Forging', 'solution'],
    ['Weaving', 'words'],
    ['Painting', 'picture'],
    ['Composing', 'symphony'],
    ['Building', 'masterpiece'],
    ['Assembling', 'thoughts'],
    ['Writing', 'story'],
    ['Creating', 'magic'],
  ],
};

const DEFAULT_PHRASES: [string, string][] = [
  ['Processing', 'request'],
  ['Working on', 'task'],
  ['Thinking about', 'problem'],
  ['Considering', 'options'],
];

function getLoadingMessage(phase: string): string {
  const phrases: [string, string][] = LOADING_PHRASES[phase] ?? DEFAULT_PHRASES;
  const idx = Math.floor(Math.random() * phrases.length);
  const pair = phrases[idx]!;
  return `${pair[0]} the ${pair[1]}`;
}

interface TypingIndicatorProps {
  phase?: AgentPhase | null;
}

export function TypingIndicator({ phase }: TypingIndicatorProps) {
  const phaseKey = phase?.name ?? 'default';
  const [message, setMessage] = useState(() => getLoadingMessage(phaseKey));
  const [fade, setFade] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval>>(null);
  const prevPhaseRef = useRef(phaseKey);

  // Rotate message every 4s; also rotate immediately on phase change
  useEffect(() => {
    if (prevPhaseRef.current !== phaseKey) {
      prevPhaseRef.current = phaseKey;
      setMessage(getLoadingMessage(phaseKey));
      setFade(true);
    }

    intervalRef.current = setInterval(() => {
      setFade(false);
      setTimeout(() => {
        setMessage(getLoadingMessage(phaseKey));
        setFade(true);
      }, 300);
    }, 4000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [phaseKey]);

  return (
    <div className={styles.container}>
      {phase && (
        <span className={styles.phase}>
          {phase.name.charAt(0).toUpperCase() + phase.name.slice(1)}
        </span>
      )}
      <div
        className={styles.message}
        style={{ opacity: fade ? 1 : 0, transition: 'opacity 0.3s ease' }}
      >
        {message}
      </div>
      <div className={styles.dots}>
        <span className={styles.dot} />
        <span className={styles.dot} />
        <span className={styles.dot} />
      </div>
    </div>
  );
}

export default TypingIndicator;
