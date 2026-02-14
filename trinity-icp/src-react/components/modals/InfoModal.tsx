/**
 * InfoModal — reusable informational modal with variant content.
 * Used for: About, Akash Provider, ICP, Model, IPFS Storage.
 */
import styles from '../../styles/components/Modal.module.css';

export type InfoVariant = 'about' | 'akash' | 'icp' | 'model' | 'ipfs';

interface InfoModalProps {
  variant: InfoVariant;
  /** Extra data from health endpoint (model, provider, gpu) */
  data?: Record<string, unknown>;
  onClose: () => void;
}

interface Section {
  title: string;
  content: string;
}

function getContent(variant: InfoVariant, data: Record<string, unknown>): { title: string; sections: Section[] } {
  switch (variant) {
    case 'about':
      return {
        title: 'About Trinity',
        sections: [
          { title: 'Architecture', content: 'Trinity is a fully decentralized AI chat application. The frontend runs on the Internet Computer (ICP) as a canister, while the backend runs on Akash Network (decentralized cloud) with Ollama for inference.' },
          { title: 'Storage', content: 'Chats are encrypted with AES-256-GCM using your principal ID. They auto-save to the Akash backend disk and can be archived to IPFS via Lighthouse for permanent, decentralized backup.' },
          { title: 'Authentication', content: 'Ed25519 keypairs provide self-custody identity. Your private key is your password — Trinity never stores it. All API calls are cryptographically signed.' },
          { title: 'Data Flow', content: 'User Input → ICP Frontend → Cloudflare Worker (SSL) → Akash Backend → Ollama LLM → Streaming Response' },
        ],
      };
    case 'akash':
      return {
        title: 'Akash Provider',
        sections: [
          { title: 'Provider', content: String(data.provider ?? 'Unknown') },
          { title: 'GPU', content: String(data.gpu_type ?? 'Unknown') },
          { title: 'What is Akash?', content: 'Akash Network is a decentralized cloud computing marketplace. Trinity runs on Akash to ensure censorship resistance and competitive pricing for GPU compute.' },
        ],
      };
    case 'icp':
      return {
        title: 'Internet Computer (ICP)',
        sections: [
          { title: 'What is ICP?', content: 'The Internet Computer is a blockchain that hosts smart contracts (canisters) serving web content at web speed. Trinity\'s frontend runs entirely on-chain.' },
          { title: 'Canister', content: 'The frontend canister serves HTML, CSS, and JavaScript directly to your browser with no traditional server.' },
        ],
      };
    case 'model':
      return {
        title: 'AI Model',
        sections: [
          { title: 'Model', content: String(data.model ?? 'Unknown') },
          { title: 'Why Open Source?', content: 'Trinity uses open-weight models via Ollama. This ensures transparency, auditability, and freedom from proprietary API dependencies.' },
        ],
      };
    case 'ipfs':
      return {
        title: 'IPFS Storage',
        sections: [
          { title: 'How It Works', content: 'When you archive a chat, it is encrypted with your principal ID and uploaded to IPFS via Lighthouse SDK. The resulting CID (Content Identifier) is a permanent, content-addressed link.' },
          { title: 'Your Data, Your Keys', content: 'Only someone with your private key can decrypt archived chats. The storage is trustless — even Lighthouse cannot read your data.' },
        ],
      };
  }
}

export function InfoModal({ variant, data = {}, onClose }: InfoModalProps) {
  const { title, sections } = getContent(variant, data);

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <span className={styles.title}>{title}</span>
          <button className={styles.closeBtn} onClick={onClose}>&times;</button>
        </div>
        <div className={styles.body}>
          {sections.map((s) => (
            <div key={s.title} style={{ marginBottom: 'var(--space-md)' }}>
              <p style={{ fontWeight: 600, marginBottom: 4, color: 'var(--color-text-primary)' }}>
                {s.title}
              </p>
              <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem', lineHeight: 1.6, margin: 0 }}>
                {s.content}
              </p>
            </div>
          ))}
        </div>
        <div className={styles.footer}>
          <button className={styles.primaryBtn} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default InfoModal;
