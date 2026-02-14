/**
 * lighthouse.ts — IPFS/Lighthouse client-side utilities.
 *
 * The backend handles uploads; this module provides:
 *  - Multi-gateway retrieval
 *  - Status checking via backend proxy
 *  - Display helpers (CID formatting, deal status)
 */
import Logger from './logger';

// ── Configuration ──────────────────────────────────────────────────────

const IPFS_GATEWAYS = [
  'https://gateway.lighthouse.storage/ipfs',
  'https://ipfs.io/ipfs',
  'https://dweb.link/ipfs',
  'https://cloudflare-ipfs.com/ipfs',
] as const;

const GATEWAY_TIMEOUT_MS = 30_000;

// ── Types ──────────────────────────────────────────────────────────────

export interface IPFSStatus {
  cid?: string;
  status: 'available' | 'pending' | 'error' | 'unknown';
  message: string;
  gateways: string[];
  checkedAt?: string;
}

export interface DealStatusDisplay {
  icon: string;
  text: string;
  color: string;
}

// ── IPFS Status Check ──────────────────────────────────────────────────

/**
 * Check archive availability on IPFS via the backend proxy.
 */
export async function checkIPFSStatus(
  cid: string,
  apiBaseUrl: string
): Promise<IPFSStatus> {
  if (!cid) {
    return { status: 'error', message: 'No CID provided', gateways: [] };
  }

  try {
    const response = await fetch(`${apiBaseUrl}/chat/archive/status/${cid}`, {
      headers: { Accept: 'application/json' },
    });

    if (!response.ok) {
      throw new Error(`Status check failed: ${response.status}`);
    }

    const data = await response.json();
    Logger.debug(`IPFS status for ${cid.substring(0, 12)}...:`, data.status);

    return {
      cid: data.cid,
      status: data.status ?? 'available',
      message: data.message ?? 'Available on IPFS',
      gateways: data.gateways ?? getGatewayUrls(cid),
      checkedAt: data.checkedAt,
    };
  } catch (error) {
    Logger.error('IPFS status check failed:', error);
    return {
      status: 'error',
      message: (error as Error).message,
      gateways: getGatewayUrls(cid),
    };
  }
}

// ── Gateway Utilities ──────────────────────────────────────────────────

/** Get redundant gateway URLs for a CID. */
export function getGatewayUrls(cid: string): string[] {
  if (!cid) return [];
  return IPFS_GATEWAYS.map((gw) => `${gw}/${cid}`);
}

/**
 * Retrieve content from IPFS, trying gateways in order.
 * @throws if all gateways fail
 */
export async function retrieveFromIPFS(cid: string): Promise<string> {
  if (!cid) throw new Error('No CID provided');

  const urls = getGatewayUrls(cid);
  const errors: string[] = [];

  for (const url of urls) {
    try {
      Logger.debug(`Trying IPFS gateway: ${url}`);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);

      const response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: 'application/json, text/plain, */*' },
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const content = await response.text();
        Logger.debug(`Retrieved from: ${url}`);
        return content;
      }
      errors.push(`${url}: HTTP ${response.status}`);
    } catch (err) {
      const e = err as Error;
      errors.push(
        `${url}: ${e.name === 'AbortError' ? 'Timeout' : e.message}`
      );
      Logger.warn(`Gateway failed: ${url}`, e.message);
    }
  }

  throw new Error(
    `All IPFS gateways failed for CID ${cid}:\n${errors.join('\n')}`
  );
}

// ── Display Helpers ────────────────────────────────────────────────────

/** Human-friendly deal status. */
export function formatDealStatus(status: string): DealStatusDisplay {
  switch (status) {
    case 'active':
      return { icon: '✅', text: 'Stored on IPFS', color: '#4ade80' };
    case 'pending':
      return { icon: '⏳', text: 'Uploading to IPFS...', color: '#fbbf24' };
    case 'error':
      return { icon: '❌', text: 'Status check failed', color: '#f87171' };
    default:
      return { icon: '❓', text: 'Status unknown', color: '#9ca3af' };
  }
}

/** Truncate a CID for display: `QmXy...abc123`. */
export function formatCID(
  cid: string,
  prefixLen = 8,
  suffixLen = 6
): string {
  if (!cid || cid.length <= prefixLen + suffixLen + 3) return cid ?? '';
  return `${cid.substring(0, prefixLen)}...${cid.substring(cid.length - suffixLen)}`;
}

export { IPFS_GATEWAYS };
