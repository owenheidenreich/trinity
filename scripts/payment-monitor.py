#!/usr/bin/env python3
"""
Trinity Payment Monitor
=======================

Monitors the Akash wallet for incoming payments and triggers private session deployments.

How it works:
1. Queries Akash blockchain for recent transactions to our wallet
2. Parses tx memos for session requests: "trinity:tier:X:session_id"
3. Triggers deploy-private-session.sh when valid payment detected
4. Stores processed tx hashes to avoid duplicate deployments

Usage:
    python3 scripts/payment-monitor.py [--daemon]

Memo Format:
    trinity:tier:<1|2|3>:<session_id>
    
Example:
    trinity:tier:1:sess_abc123  → Deploy Tier 1 for session sess_abc123
"""

import os
import sys
import json
import time
import logging
import subprocess
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List

# Configuration
WALLET_ADDRESS = os.getenv('AKASH_WALLET_ADDRESS', 'akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp')
LCD_ENDPOINT = 'https://rest.cosmos.directory/akash'
POLL_INTERVAL = 30  # seconds between checks
PROCESSED_TX_FILE = Path(__file__).parent.parent / 'data' / 'processed_payments.json'
DEPLOY_SCRIPT = Path(__file__).parent / 'deploy-private-session.sh'

# Active sessions storage
ACTIVE_SESSIONS_FILE = Path(__file__).parent.parent / 'data' / 'active_sessions.json'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('payment-monitor')


def ensure_data_dir():
    """Create data directory if it doesn't exist."""
    data_dir = PROCESSED_TX_FILE.parent
    data_dir.mkdir(parents=True, exist_ok=True)


def load_processed_txs() -> set:
    """Load set of already-processed transaction hashes."""
    if PROCESSED_TX_FILE.exists():
        try:
            with open(PROCESSED_TX_FILE) as f:
                return set(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load processed txs: {e}")
    return set()


def save_processed_txs(tx_hashes: set):
    """Save processed transaction hashes."""
    ensure_data_dir()
    with open(PROCESSED_TX_FILE, 'w') as f:
        json.dump(list(tx_hashes), f)


def load_active_sessions() -> Dict:
    """Load active session data."""
    if ACTIVE_SESSIONS_FILE.exists():
        try:
            with open(ACTIVE_SESSIONS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_active_sessions(sessions: Dict):
    """Save active session data."""
    ensure_data_dir()
    with open(ACTIVE_SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)


def parse_memo(memo: str) -> Optional[Dict]:
    """
    Parse payment memo for session request.
    
    Format: trinity:tier:<1|2|3>:<session_id>
    Returns: {'tier': int, 'session_id': str} or None
    """
    if not memo or not memo.startswith('trinity:tier:'):
        return None
    
    parts = memo.split(':')
    if len(parts) < 4:
        return None
    
    try:
        tier = int(parts[2])
        if tier not in [1, 2, 3]:
            return None
        
        session_id = parts[3]
        if not session_id:
            return None
        
        return {'tier': tier, 'session_id': session_id}
    except (ValueError, IndexError):
        return None


def get_recent_transactions() -> List[Dict]:
    """
    Query recent transactions sent TO our wallet.
    Returns list of transactions with amount and memo.
    """
    try:
        # Query for receive events
        response = requests.get(
            f"{LCD_ENDPOINT}/cosmos/tx/v1beta1/txs",
            params={
                'events': f"transfer.recipient='{WALLET_ADDRESS}'",
                'order_by': 'ORDER_BY_DESC',
                'pagination.limit': '20'
            },
            timeout=30
        )
        
        if response.status_code != 200:
            logger.warning(f"Failed to query transactions: {response.status_code}")
            return []
        
        data = response.json()
        transactions = []
        
        for tx_response in data.get('tx_responses', []):
            tx = data.get('txs', [])[data.get('tx_responses', []).index(tx_response)] if 'txs' in data else {}
            
            # Get memo from tx body
            memo = tx.get('body', {}).get('memo', '')
            
            # Get amount from logs
            amount_uakt = 0
            for log in tx_response.get('logs', []):
                for event in log.get('events', []):
                    if event.get('type') == 'transfer':
                        for attr in event.get('attributes', []):
                            if attr.get('key') == 'amount':
                                # Parse "1000000uakt" format
                                amount_str = attr.get('value', '')
                                if 'uakt' in amount_str:
                                    amount_uakt = int(amount_str.replace('uakt', ''))
            
            transactions.append({
                'hash': tx_response.get('txhash'),
                'height': tx_response.get('height'),
                'timestamp': tx_response.get('timestamp'),
                'memo': memo,
                'amount_uakt': amount_uakt,
                'amount_akt': amount_uakt / 1_000_000
            })
        
        return transactions
        
    except Exception as e:
        logger.error(f"Error querying transactions: {e}")
        return []


def deploy_session(tier: int, payment_akt: float, session_id: str) -> Optional[Dict]:
    """
    Trigger private session deployment.
    Returns deployment result or None on failure.
    """
    logger.info(f"🚀 Deploying session: tier={tier}, payment={payment_akt} AKT, id={session_id}")
    
    try:
        result = subprocess.run(
            [str(DEPLOY_SCRIPT), str(tier), str(payment_akt), session_id],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Deployment failed: {result.stderr}")
            return None
        
        # Parse JSON output
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error(f"Invalid deployment output: {result.stdout}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("Deployment timed out")
        return None
    except Exception as e:
        logger.error(f"Deployment error: {e}")
        return None


def cleanup_expired_sessions():
    """Close expired sessions and cleanup."""
    sessions = load_active_sessions()
    now = datetime.now(timezone.utc)
    expired = []
    
    for session_id, session in sessions.items():
        expiry = datetime.fromisoformat(session['expires_at'].replace('Z', '+00:00'))
        if now > expiry:
            expired.append(session_id)
    
    for session_id in expired:
        session = sessions[session_id]
        dseq = session.get('dseq')
        
        logger.info(f"⏰ Session {session_id} expired, closing deployment {dseq}")
        
        try:
            subprocess.run(
                [str(DEPLOY_SCRIPT), 'close', dseq],
                capture_output=True,
                timeout=60
            )
        except Exception as e:
            logger.error(f"Failed to close deployment: {e}")
        
        del sessions[session_id]
    
    if expired:
        save_active_sessions(sessions)
        logger.info(f"✅ Cleaned up {len(expired)} expired sessions")


def process_payments():
    """Check for new payments and deploy sessions."""
    processed = load_processed_txs()
    sessions = load_active_sessions()
    
    transactions = get_recent_transactions()
    
    for tx in transactions:
        tx_hash = tx['hash']
        
        # Skip already processed
        if tx_hash in processed:
            continue
        
        # Parse memo for session request
        session_info = parse_memo(tx['memo'])
        if not session_info:
            continue
        
        tier = session_info['tier']
        session_id = session_info['session_id']
        payment_akt = tx['amount_akt']
        
        logger.info(f"💰 Payment detected: {payment_akt} AKT for tier {tier} session {session_id}")
        
        # Deploy session
        result = deploy_session(tier, payment_akt, session_id)
        
        if result and result.get('success'):
            # Store active session
            sessions[session_id] = result
            save_active_sessions(sessions)
            logger.info(f"✅ Session deployed: {result.get('endpoint')}")
        else:
            logger.error(f"❌ Failed to deploy session for tx {tx_hash}")
        
        # Mark as processed regardless of success (don't retry failed payments)
        processed.add(tx_hash)
    
    save_processed_txs(processed)


def run_daemon():
    """Run as background daemon, polling for payments."""
    logger.info("🔍 Starting payment monitor daemon")
    logger.info(f"   Wallet: {WALLET_ADDRESS}")
    logger.info(f"   Poll interval: {POLL_INTERVAL}s")
    
    while True:
        try:
            # Cleanup expired sessions first
            cleanup_expired_sessions()
            
            # Process new payments
            process_payments()
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        
        time.sleep(POLL_INTERVAL)


def main():
    """Main entry point."""
    ensure_data_dir()
    
    if '--daemon' in sys.argv:
        run_daemon()
    else:
        # Single check mode
        logger.info("Running single payment check...")
        cleanup_expired_sessions()
        process_payments()
        
        # Print active sessions
        sessions = load_active_sessions()
        if sessions:
            print("\nActive Sessions:")
            for sid, s in sessions.items():
                print(f"  {sid}: {s.get('tier_name')} - expires {s.get('expires_at')}")
        else:
            print("\nNo active sessions")


if __name__ == '__main__':
    main()
