/**
 * Lighthouse/IPFS utility tests.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  getGatewayUrls,
  formatDealStatus,
  formatCID,
  checkIPFSStatus,
  retrieveFromIPFS,
  IPFS_GATEWAYS,
} from '../utils/lighthouse';

describe('lighthouse utilities', () => {
  describe('getGatewayUrls', () => {
    it('returns gateway URLs for a CID', () => {
      const urls = getGatewayUrls('QmTestCid123');
      expect(urls).toHaveLength(IPFS_GATEWAYS.length);
      expect(urls[0]).toContain('QmTestCid123');
      expect(urls[0]).toContain('gateway.lighthouse.storage');
    });

    it('returns empty array for empty CID', () => {
      expect(getGatewayUrls('')).toEqual([]);
    });
  });

  describe('formatDealStatus', () => {
    it('formats active status', () => {
      const status = formatDealStatus('active');
      expect(status.text).toBe('Stored on IPFS');
      expect(status.color).toBe('#4ade80');
    });

    it('formats pending status', () => {
      const status = formatDealStatus('pending');
      expect(status.text).toBe('Uploading to IPFS...');
      expect(status.color).toBe('#fbbf24');
    });

    it('formats error status', () => {
      const status = formatDealStatus('error');
      expect(status.text).toBe('Status check failed');
      expect(status.color).toBe('#f87171');
    });

    it('formats unknown status', () => {
      const status = formatDealStatus('something-else');
      expect(status.text).toBe('Status unknown');
    });
  });

  describe('formatCID', () => {
    it('truncates long CIDs', () => {
      const cid = 'QmXyZ1234567890abcdefghijklmnopqrstuvwxyz';
      const formatted = formatCID(cid);
      expect(formatted).toContain('...');
      expect(formatted.length).toBeLessThan(cid.length);
    });

    it('returns short CIDs unchanged when under threshold', () => {
      // prefixLen(8) + suffixLen(6) + 3 = 17, so anything <= 17 chars returns as-is
      expect(formatCID('QmShortCID')).toBe('QmShortCID');
    });

    it('handles empty CID', () => {
      expect(formatCID('')).toBe('');
    });

    it('accepts custom prefix/suffix lengths', () => {
      const cid = 'QmXyZ1234567890abcdefghijklmnopqrstuvwxyz';
      const formatted = formatCID(cid, 4, 4);
      expect(formatted).toBe('QmXy...wxyz');
    });
  });

  describe('checkIPFSStatus', () => {
    const mockFetch = vi.fn();
    beforeEach(() => {
      mockFetch.mockReset();
      vi.stubGlobal('fetch', mockFetch);
    });
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('returns status from backend', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          cid: 'Qm123',
          status: 'available',
          message: 'Available',
        }),
      });

      const result = await checkIPFSStatus('Qm123', 'http://localhost:5000');
      expect(result.status).toBe('available');
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:5000/chat/archive/status/Qm123',
        expect.objectContaining({ headers: { Accept: 'application/json' } })
      );
    });

    it('returns error for empty CID', async () => {
      const result = await checkIPFSStatus('', 'http://localhost:5000');
      expect(result.status).toBe('error');
      expect(result.message).toBe('No CID provided');
    });

    it('handles fetch failure', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));
      const result = await checkIPFSStatus('Qm123', 'http://localhost:5000');
      expect(result.status).toBe('error');
      expect(result.message).toContain('Network error');
    });
  });

  describe('retrieveFromIPFS', () => {
    const mockFetch = vi.fn();
    beforeEach(() => {
      mockFetch.mockReset();
      vi.stubGlobal('fetch', mockFetch);
    });
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('throws for empty CID', async () => {
      await expect(retrieveFromIPFS('')).rejects.toThrow('No CID provided');
    });

    it('returns content from first successful gateway', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        text: async () => '{"encrypted": "data"}',
      });

      const content = await retrieveFromIPFS('QmTest');
      expect(content).toBe('{"encrypted": "data"}');
      // Should have called the first gateway
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('tries next gateway on failure', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: false, status: 404 })
        .mockResolvedValueOnce({
          ok: true,
          text: async () => 'content',
        });

      const content = await retrieveFromIPFS('QmTest');
      expect(content).toBe('content');
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it('throws when all gateways fail', async () => {
      mockFetch.mockResolvedValue({ ok: false, status: 500 });

      await expect(retrieveFromIPFS('QmTest')).rejects.toThrow(
        'All IPFS gateways failed'
      );
    });
  });
});
