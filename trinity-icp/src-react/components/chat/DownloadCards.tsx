/**
 * DownloadCards — renders file download cards for tool-generated outputs.
 * Claude-style cards at the bottom of an assistant message.
 */
import { useCallback } from 'react';
import styles from '../../styles/components/DownloadCards.module.css';

export interface DownloadFile {
  filename: string;
  content: string;
  mimeType?: string;
}

interface DownloadCardsProps {
  files: DownloadFile[];
}

const EXTENSION_ICONS: Record<string, string> = {
  py: '🐍',
  js: '📜',
  ts: '📜',
  json: '{}',
  md: '📝',
  html: '🌐',
  css: '🎨',
  txt: '📄',
  csv: '📊',
};

function getExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() ?? '';
}

function getIcon(filename: string): string {
  return EXTENSION_ICONS[getExtension(filename)] ?? '📄';
}

function getFileType(filename: string): string {
  const ext = getExtension(filename);
  return ext ? ext.toUpperCase() : 'FILE';
}

export function DownloadCards({ files }: DownloadCardsProps) {
  if (!files.length) return null;

  return (
    <div className={styles.container}>
      {files.map((file, i) => (
        <DownloadCard key={`${file.filename}-${i}`} file={file} />
      ))}
    </div>
  );
}

function DownloadCard({ file }: { file: DownloadFile }) {
  const handleDownload = useCallback(() => {
    const mime = file.mimeType ?? 'text/plain';
    const blob = new Blob([file.content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = file.filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [file]);

  return (
    <div className={styles.card}>
      <div className={styles.icon}>
        <span className={styles.glyph}>{getIcon(file.filename)}</span>
      </div>
      <div className={styles.info}>
        <span className={styles.name}>{file.filename}</span>
        <span className={styles.type}>{getFileType(file.filename)}</span>
      </div>
      <button className={styles.downloadBtn} onClick={handleDownload}>
        Download
      </button>
    </div>
  );
}

export default DownloadCards;
