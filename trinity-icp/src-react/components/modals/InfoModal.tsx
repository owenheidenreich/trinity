/**
 * InfoModal — rich informational modals ported from old modals.js.
 * Used for: About, Akash Provider, ICP, Model, IPFS Storage.
 * Now includes full content: external links, technical details, code blocks, lists.
 */
import styles from '../../styles/components/Modal.module.css';

export type InfoVariant = 'about' | 'akash' | 'icp' | 'model' | 'ipfs';

interface InfoModalProps {
  variant: InfoVariant;
  /** Extra data from health endpoint (model, provider, gpu) */
  data?: Record<string, unknown>;
  onClose: () => void;
}

const CANISTER_ID = 'zc67k-kiaaa-aaaal-qtmiq-cai';
const BACKEND_CANISTER_ID = 'au5zq-2qaaa-aaaal-qtowa-cai';

const monoStyle: React.CSSProperties = {
  background: '#1a1a1a',
  padding: '12px',
  borderRadius: '6px',
  fontSize: '11px',
  lineHeight: 1.8,
  fontFamily: 'monospace',
  wordBreak: 'break-all',
  marginTop: '8px',
};

const listStyle: React.CSSProperties = {
  margin: '8px 0 0 0',
  paddingLeft: '20px',
  color: '#aaa',
  fontSize: '12px',
  lineHeight: 1.6,
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <h4 style={{ margin: '0 0 6px 0', color: 'var(--color-text-primary)', fontSize: '0.9rem' }}>
        {title}
      </h4>
      <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.85rem', lineHeight: 1.6 }}>
        {children}
      </div>
    </div>
  );
}

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: '#69db7c', textDecoration: 'none' }}
    >
      {children} ↗
    </a>
  );
}

function renderAbout() {
  return {
    title: 'About Trinity',
    subtitle: 'Decentralized AI chat — no accounts, no tracking, your keys',
    content: (
      <>
        <Section title="Frontend — ICP Canister">
          <p style={{ margin: 0 }}>
            This interface runs on an Internet Computer canister — a tamper-proof smart contract that serves HTML/JS globally without traditional servers.
          </p>
        </Section>
        <Section title="Backend — Akash Network">
          <p style={{ margin: 0 }}>
            AI inference (Ollama) runs on Akash&apos;s decentralized GPU cloud. Your messages are processed without any single company controlling access.
          </p>
        </Section>
        <Section title="Storage — Encrypted Autosave">
          <p style={{ margin: 0 }}>
            Chats autosave encrypted (AES-256-GCM) to Akash disk. Only your keypair can decrypt them. You can also archive permanently to IPFS via Lighthouse.
          </p>
        </Section>
        <Section title="Auth — Ed25519 Keypair">
          <p style={{ margin: 0 }}>
            No passwords or accounts. Your browser generates an Ed25519 keypair. Export the private key anytime to back up or migrate.
          </p>
        </Section>
        <Section title="Data Flow">
          <pre style={{ ...monoStyle, overflowX: 'auto', whiteSpace: 'pre' }}>
{`Browser → ICP Canister → Cloudflare → Akash GPU → Ollama LLM
                              ↓
                   Encrypted Autosave → Akash Disk`}
          </pre>
        </Section>
        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <ExternalLink href="https://internetcomputer.org">ICP</ExternalLink>
          {' · '}
          <ExternalLink href="https://akash.network">Akash</ExternalLink>
          {' · '}
          <ExternalLink href="https://ipfs.tech">IPFS</ExternalLink>
        </div>
      </>
    ),
  };
}

function renderAkash(data: Record<string, unknown>) {
  const provider = String(data.provider ?? 'Unknown');
  const gpuType = String(data.gpu_type ?? 'Unknown');
  const model = String(data.model ?? 'Unknown');

  return {
    title: 'Akash Provider',
    subtitle: 'Your AI runs on decentralized compute',
    content: (
      <>
        <Section title={`Provider: ${provider}`}>
          <p style={{ margin: 0 }}>
            This is an <strong>audited Akash provider</strong> — a verified data center operator participating in the Akash decentralized cloud marketplace.
          </p>
        </Section>
        <Section title="Audited Attributes">
          <p style={{ margin: 0 }}>
            Akash providers can be audited by trusted parties who verify their hardware, uptime, and security practices:
          </p>
          <ul style={listStyle}>
            <li><strong>Hardware verification:</strong> GPU type and count confirmed</li>
            <li><strong>Geographic location:</strong> Data center location verified</li>
            <li><strong>Uptime history:</strong> Historical availability tracked</li>
            <li><strong>Security practices:</strong> Isolation and data handling audited</li>
          </ul>
        </Section>
        <Section title="Your Session">
          <div style={monoStyle}>
            <div><span style={{ color: '#888' }}>Provider:</span> <span style={{ color: '#ff6b6b' }}>{provider}</span></div>
            <div><span style={{ color: '#888' }}>GPU:</span> <span style={{ color: '#69db7c' }}>{gpuType}</span></div>
            <div><span style={{ color: '#888' }}>Model:</span> <span style={{ color: '#a78bfa' }}>{model}</span></div>
          </div>
        </Section>
        <Section title="Why Decentralized Compute?">
          <p style={{ margin: 0 }}>
            Unlike centralized cloud providers (AWS, Google, Azure), Akash is a permissionless marketplace. Anyone can provide compute, and anyone can deploy. No single entity can censor or shut down your AI.
          </p>
        </Section>
        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <ExternalLink href="https://console.akash.network/providers">View All Providers</ExternalLink>
        </div>
      </>
    ),
  };
}

function renderICP() {
  return {
    title: 'Internet Computer',
    subtitle: 'Your frontend runs on the world computer',
    content: (
      <>
        <Section title="What is ICP?">
          <p style={{ margin: 0 }}>
            The Internet Computer is a blockchain that runs at web speed. Unlike traditional blockchains, it can host entire web applications — frontend, backend, and data — all on-chain.
          </p>
        </Section>
        <Section title="Your Canister">
          <div style={monoStyle}>
            <div><span style={{ color: '#888' }}>Frontend:</span> <span style={{ color: '#5ac8fa' }}>{CANISTER_ID}</span></div>
            <div style={{ marginTop: '4px' }}><span style={{ color: '#888' }}>Backend:</span> <span style={{ color: '#5ac8fa' }}>{BACKEND_CANISTER_ID}</span></div>
          </div>
          <p style={{ marginTop: '8px', fontSize: '11px', color: '#666' }}>
            Canisters are smart contracts that can serve web content. Your entire Trinity interface is hosted here.
          </p>
        </Section>
        <Section title="Why It Matters">
          <ul style={listStyle}>
            <li><strong>Censorship resistant:</strong> No single company can take it down</li>
            <li><strong>No servers:</strong> Runs on a decentralized network of nodes</li>
            <li><strong>Tamper-proof:</strong> Code is verified by blockchain consensus</li>
            <li><strong>Always available:</strong> No cloud provider outages</li>
          </ul>
        </Section>
        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <ExternalLink href={`https://dashboard.internetcomputer.org/canister/${CANISTER_ID}`}>View Canister</ExternalLink>
        </div>
      </>
    ),
  };
}

function renderModel(data: Record<string, unknown>) {
  const modelName = String(data.model ?? 'Unknown');
  const gpuType = String(data.gpu_type ?? 'Unknown');

  const isLlama = modelName.toLowerCase().includes('llama');
  const isQwen = modelName.toLowerCase().includes('qwen');
  const is70B = /70b/i.test(modelName) || /72b/i.test(modelName);
  const is14B = /14b/i.test(modelName);
  const is8B = /8b/i.test(modelName);

  let modelFamily = 'Unknown';
  let modelDescription = 'A large language model running on decentralized infrastructure.';
  let modelLink = 'https://ollama.com/library';

  if (isLlama) {
    modelFamily = 'Meta Llama';
    modelDescription = "Meta's open-source Llama model, one of the most capable open LLMs available. Trained on publicly available data with strong reasoning and coding abilities.";
    modelLink = 'https://llama.meta.com';
  } else if (isQwen) {
    modelFamily = 'Alibaba Qwen';
    modelDescription = "Alibaba's Qwen model series, known for strong multilingual capabilities and competitive performance with proprietary models.";
    modelLink = 'https://qwenlm.github.io';
  }

  let sizeInfo = '';
  if (is70B) sizeInfo = '70–72 billion parameters — requires significant GPU memory, offers highest quality responses.';
  else if (is14B) sizeInfo = '14 billion parameters — strong balance of quality and speed.';
  else if (is8B) sizeInfo = '8 billion parameters — efficient and fast while maintaining strong capabilities.';

  return {
    title: 'AI Model',
    subtitle: 'Open-source AI running on your terms',
    content: (
      <>
        <Section title="Current Model">
          <div style={monoStyle}>
            <div><span style={{ color: '#888' }}>Model:</span> <span style={{ color: '#a78bfa' }}>{modelName}</span></div>
            <div><span style={{ color: '#888' }}>Family:</span> <span style={{ color: '#a78bfa' }}>{modelFamily}</span></div>
            <div><span style={{ color: '#888' }}>GPU:</span> <span style={{ color: '#69db7c' }}>{gpuType}</span></div>
          </div>
        </Section>
        <Section title="About This Model">
          <p style={{ margin: 0 }}>{modelDescription}</p>
          {sizeInfo && <p style={{ marginTop: '8px', fontSize: '12px', color: '#888' }}>{sizeInfo}</p>}
        </Section>
        <Section title="Why Open Source?">
          <ul style={listStyle}>
            <li><strong>Transparent:</strong> Anyone can inspect the model weights</li>
            <li><strong>No censorship:</strong> No corporate content policies</li>
            <li><strong>Self-hostable:</strong> Run it yourself if you want</li>
            <li><strong>Privacy:</strong> Your prompts never leave this infrastructure</li>
          </ul>
        </Section>
        <Section title="Powered by Ollama">
          <p style={{ margin: 0 }}>
            Trinity uses Ollama to run models locally on GPU. No API calls to OpenAI, Anthropic, or other centralized providers.
          </p>
        </Section>
        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <ExternalLink href={modelLink}>Learn More</ExternalLink>
        </div>
      </>
    ),
  };
}

function renderIPFS() {
  return {
    title: 'IPFS Storage',
    subtitle: 'Your archives live forever on decentralized storage',
    content: (
      <>
        <Section title="The Storage Stack">
          <div style={monoStyle}>
            <div><span style={{ color: '#69db7c' }}>Lighthouse SDK</span> <span style={{ color: '#666' }}>→ handles uploads &amp; pinning</span></div>
            <div><span style={{ color: '#69db7c' }}>IPFS</span> <span style={{ color: '#666' }}>→ content-addressed permanent storage</span></div>
          </div>
        </Section>
        <Section title="How It Works">
          <p style={{ margin: 0 }}>
            When you archive a chat, Lighthouse uploads it to IPFS and pins it permanently. The CID (Content ID) is your permanent address — anyone with it can retrieve your encrypted data from any IPFS gateway worldwide.
          </p>
        </Section>
        <Section title="Why Lighthouse?">
          <ul style={listStyle}>
            <li><strong>Easy integration:</strong> Simple SDK for developers</li>
            <li><strong>Verified deals:</strong> Confirms data is actually stored</li>
            <li><strong>Encryption:</strong> Optional client-side encryption</li>
            <li><strong>Perpetual storage:</strong> Deals auto-renew</li>
          </ul>
        </Section>
        <Section title="Your Data, Your Keys">
          <p style={{ margin: 0 }}>
            Archives are encrypted with your principal ID before upload. Only you can decrypt them. Lighthouse and IPFS nodes see only encrypted bytes.
          </p>
        </Section>
        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <ExternalLink href="https://docs.lighthouse.storage">Lighthouse Docs</ExternalLink>
        </div>
      </>
    ),
  };
}

export function InfoModal({ variant, data = {}, onClose }: InfoModalProps) {
  const renderers: Record<InfoVariant, () => { title: string; subtitle: string; content: React.ReactNode }> = {
    about: renderAbout,
    akash: () => renderAkash(data),
    icp: renderICP,
    model: () => renderModel(data),
    ipfs: renderIPFS,
  };

  const { title, subtitle, content } = renderers[variant]();

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <span className={styles.title}>{title}</span>
          <button className={styles.closeBtn} onClick={onClose}>&times;</button>
        </div>
        <div className={styles.body}>
          <p style={{
            textAlign: 'center',
            color: '#aaa',
            marginBottom: '20px',
            fontSize: '0.85rem',
          }}>
            {subtitle}
          </p>
          {content}
        </div>
        <div className={styles.footer}>
          <button className={styles.primaryBtn} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default InfoModal;
