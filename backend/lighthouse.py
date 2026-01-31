"""
Trinity Backend - Lighthouse/Filecoin Module
IPFS pinning + Filecoin verified storage via Lighthouse
"""

import logging
import requests
from typing import Optional

from config import LIGHTHOUSE_API_KEY, LIGHTHOUSE_NODE, LIGHTHOUSE_API, LIGHTHOUSE_GATEWAY

logger = logging.getLogger(__name__)


def upload_to_filecoin(file_data: bytes, filename: str, principal_id: str = None, is_master_bundle: bool = False) -> Optional[str]:
    """
    Upload file to IPFS + Filecoin via Lighthouse.
    
    Lighthouse automatically queues uploaded content for Filecoin verified deals.
    The CID is available immediately via IPFS; Filecoin deal seals in 1-24 hours.

    Args:
        file_data: The encrypted data to upload
        filename: Name for the file (used for tracking)
        principal_id: User's principal ID (for logging)
        is_master_bundle: If True, marks this as the user's master bundle

    Returns:
        CID string on success, None on failure
    """
    if not LIGHTHOUSE_API_KEY:
        logger.warning('Lighthouse API key not configured - skipping archive')
        return None

    try:
        endpoint = f'{LIGHTHOUSE_NODE}/api/v0/add'
        
        headers = {
            'Authorization': f'Bearer {LIGHTHOUSE_API_KEY}'
        }
        
        files = {
            'file': (filename, file_data, 'application/json')
        }
        
        logger.info(f'📤 Uploading to Lighthouse: {filename} ({len(file_data)} bytes)')
        
        response = requests.post(
            endpoint,
            headers=headers,
            files=files,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            cid = result.get('Hash')
            size = result.get('Size', len(file_data))
            
            logger.info(f'✅ Uploaded to Lighthouse/IPFS: {cid}')
            logger.info(f'   Size: {size} bytes')
            logger.info(f'   Principal: {principal_id}')
            logger.info(f'   Gateway: {LIGHTHOUSE_GATEWAY}/ipfs/{cid}')
            
            return cid
        else:
            logger.error(f'❌ Lighthouse upload failed: {response.status_code} - {response.text}')
            return None

    except requests.Timeout:
        logger.error('❌ Lighthouse upload timed out')
        return None
    except Exception as e:
        logger.error(f'❌ Lighthouse upload error: {e}', exc_info=True)
        return None


def get_lighthouse_uploads(principal_id: str = None, file_type: str = None) -> list:
    """
    Get list of files uploaded to Lighthouse for this API key.

    Args:
        principal_id: User's principal ID (for logging)
        file_type: Optional filter (not used in API, filter locally)

    Returns:
        List of upload records sorted by upload time (newest first)
    """
    if not LIGHTHOUSE_API_KEY:
        logger.warning('Lighthouse API key not configured')
        return []

    try:
        headers = {
            'Authorization': f'Bearer {LIGHTHOUSE_API_KEY}'
        }

        response = requests.get(
            f'{LIGHTHOUSE_API}/api/user/files_uploaded',
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            files = result.get('fileList', [])
            files.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
            
            logger.info(f'📦 Found {len(files)} files in Lighthouse storage')
            return files
        else:
            logger.error(f'Lighthouse listing failed: {response.status_code} - {response.text}')
            return []

    except requests.Timeout:
        logger.error('Lighthouse listing timed out')
        return []
    except Exception as e:
        logger.error(f'Lighthouse listing error: {e}', exc_info=True)
        return []


def get_filecoin_deal_status(cid: str) -> dict:
    """
    Check Filecoin deal status for a CID.
    
    Filecoin deals typically take 1-24 hours to be created and sealed.

    Args:
        cid: IPFS content identifier

    Returns:
        Dict with deal status information
    """
    if not cid:
        return {'status': 'error', 'message': 'No CID provided'}

    try:
        response = requests.get(
            f'{LIGHTHOUSE_API}/api/lighthouse/deal_status?cid={cid}',
            timeout=30
        )

        if response.status_code == 200:
            deals = response.json()
            
            if not deals or len(deals) == 0:
                return {
                    'status': 'pending',
                    'message': 'Filecoin deal not yet created (can take 1-24 hours)',
                    'deals': []
                }
            
            return {
                'status': 'active',
                'message': 'Stored on Filecoin',
                'deals': deals
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Could not check deal status: {response.status_code}',
                'deals': []
            }

    except Exception as e:
        logger.error(f'Deal status check failed: {e}')
        return {
            'status': 'error',
            'message': str(e),
            'deals': []
        }


def download_from_filecoin(cid: str) -> Optional[bytes]:
    """
    Download file from IPFS via multiple gateways for redundancy.
    
    Tries Lighthouse gateway first since we upload there, then falls back
    to other public IPFS gateways for redundancy.
    """
    if not cid:
        return None

    try:
        gateways = [
            f'{LIGHTHOUSE_GATEWAY}/ipfs/{cid}',
            f'https://ipfs.io/ipfs/{cid}',
            f'https://dweb.link/ipfs/{cid}',
            f'https://cloudflare-ipfs.com/ipfs/{cid}'
        ]

        for gateway in gateways:
            try:
                logger.info(f'Attempting download from: {gateway}')
                response = requests.get(gateway, timeout=30)

                if response.status_code == 200:
                    logger.info(f'✅ File downloaded from IPFS: {cid}')
                    return response.content
                else:
                    logger.warning(f'Gateway {gateway} returned {response.status_code}')
            except requests.Timeout:
                logger.warning(f'Gateway {gateway} timed out')
                continue
            except Exception as e:
                logger.warning(f'Gateway {gateway} error: {e}')
                continue

        logger.error(f'❌ All gateways failed for CID: {cid}')
        return None
    except Exception as e:
        logger.error(f'❌ IPFS download error: {e}', exc_info=True)
        return None
