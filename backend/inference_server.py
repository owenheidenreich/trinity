"""
Trinity Inference Server
Production backend using Ollama for model inference

Refactored: Config, encryption, storage, and lighthouse modules extracted.
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from functools import wraps
import requests
import logging
import time
import os
import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple, Optional
import threading
from apscheduler.schedulers.background import BackgroundScheduler

# Import extracted modules
from config import (
    PROVIDER_ID, MODEL_NAME, MODEL_BACKEND, GPU_TYPE, OLLAMA_HOST,
    MAX_QUEUE_SIZE, CHATS_DIR, LIGHTHOUSE_API_KEY, LIGHTHOUSE_NODE,
    LIGHTHOUSE_API, LIGHTHOUSE_GATEWAY, AKASH_WALLET_ADDRESS,
    ICP_BACKEND_CANISTER, DEPLOYMENT_TIER, BUILD_TIMESTAMP,
    AUTH_TIMESTAMP_WINDOW_MS, logger
)
from encryption import EncryptionUtils
from storage import (
    get_user_dir, get_metadata_path, get_user_memory_path,
    load_user_memory, save_user_memory, load_metadata, save_metadata
)
from lighthouse import (
    upload_to_filecoin, get_lighthouse_uploads,
    get_filecoin_deal_status, download_from_filecoin
)

# Audio transcription
import tempfile
try:
    import whisper
    WHISPER_MODEL = None
    WHISPER_AVAILABLE = True
    logger.info('✅ Whisper library available')
except ImportError:
    WHISPER_AVAILABLE = False
    WHISPER_MODEL = None
    logger.warning('⚠️ Whisper not installed - audio transcription disabled')

# ICP Authentication
from icp_auth import require_auth, verify_request_auth

app = Flask(__name__)
CORS(app)

# ===== GLOBAL STATE =====

# In-memory document storage for Chat With Documents (per-session)
document_store = {}

# ===== METRICS TRACKING =====
class MetricsCollector:
    """Track performance metrics for monitoring and load balancing"""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_tokens_generated = 0
        self.total_latency_ms = 0
        self.active_requests = 0
        self.start_time = time.time()
    
    def record_request(self, success: bool, tokens: int, latency_ms: float):
        """Record metrics for a completed request"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_tokens_generated += tokens
            self.total_latency_ms += latency_ms
        else:
            self.failed_requests += 1
    
    def start_request(self):
        """Increment active request counter"""
        self.active_requests += 1
    
    def end_request(self):
        """Decrement active request counter"""
        self.active_requests = max(0, self.active_requests - 1)
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        uptime = time.time() - self.start_time
        avg_latency = (self.total_latency_ms / self.successful_requests 
                      if self.successful_requests > 0 else 0)
        
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': (self.successful_requests / self.total_requests * 100 
                            if self.total_requests > 0 else 100),
            'total_tokens_generated': self.total_tokens_generated,
            'avg_latency_ms': avg_latency,
            'active_requests': self.active_requests,
            'uptime_seconds': uptime,
        }

# Initialize metrics
metrics = MetricsCollector()

# ===== METRICS TRACKING =====

def get_system_info() -> Dict:
    """Get system resource information (CPU, memory)"""
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_available_mb': memory.available / (1024 * 1024),
        }
    except ImportError:
        logger.warning("psutil not installed - system metrics unavailable")
        return {
            'cpu_percent': 0,
            'memory_percent': 0,
            'memory_available_mb': 0,
        }

# ===== AI BACKEND INITIALIZATION =====
def check_ollama_connection() -> bool:
    """Check if Ollama is running and accessible"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return any(m['name'].startswith(MODEL_NAME) for m in models)
        return False
    except Exception as e:
        logger.error(f"Ollama connection check failed: {e}")
        return False

# ===== ICP IDEMPOTENCY CACHE =====
# ICP HTTP Outcalls require deterministic responses across 13 replicas
# We cache responses by X-Request-ID to ensure all replicas get the same response
# CRITICAL: Uses per-request locking to prevent race conditions where multiple
# replicas start LLM generation before any response is cached
class ICPIdempotencyCache:
    """Cache for ICP HTTP Outcalls - ensures all 13 replicas get identical responses"""
    
    def __init__(self, ttl_seconds: int = 30):
        self._cache: Dict[str, Tuple[Dict, int, float]] = {}  # request_id -> (response, status_code, timestamp)
        self._lock = threading.Lock()
        self._request_locks: Dict[str, threading.Lock] = {}  # Per-request locks to serialize LLM calls
        self._ttl = ttl_seconds
    
    def get(self, request_id: str) -> Optional[Tuple[Dict, int]]:
        """Get cached response if it exists and is not expired"""
        with self._lock:
            if request_id in self._cache:
                response, status_code, timestamp = self._cache[request_id]
                if time.time() - timestamp < self._ttl:
                    # DEBUG level to reduce log spam from 13 ICP replicas
                    logger.debug(f'🎯 ICP cache hit for request_id: {request_id}')
                    return response, status_code
                else:
                    del self._cache[request_id]
            return None
    
    def set(self, request_id: str, response: Dict, status_code: int):
        """Cache a response for the given request_id"""
        with self._lock:
            self._cache[request_id] = (response, status_code, time.time())
            # DEBUG level to reduce log spam from frequent ICP health checks
            logger.debug(f'💾 ICP cached response for request_id: {request_id}')
            self._cleanup()
    
    def _cleanup(self):
        """Remove expired entries"""
        now = time.time()
        expired = [rid for rid, (_, _, ts) in self._cache.items() if now - ts > self._ttl]
        for rid in expired:
            del self._cache[rid]
        # Also cleanup old request locks
        expired_locks = [rid for rid in self._request_locks if rid not in self._cache]
        for rid in expired_locks[:100]:  # Limit cleanup to prevent long locks
            del self._request_locks[rid]
    
    def get_request_lock(self, request_id: str) -> threading.Lock:
        """Get or create a lock for a specific request_id"""
        with self._lock:
            if request_id not in self._request_locks:
                self._request_locks[request_id] = threading.Lock()
            return self._request_locks[request_id]

# Global idempotency cache for ICP outcalls
icp_cache = ICPIdempotencyCache(ttl_seconds=30)

def icp_idempotent(f):
    """
    Decorator for ICP-compatible idempotent endpoints.
    Uses X-Request-ID header to return cached responses for the same request.
    This ensures all 13 ICP replicas receive identical responses.
    
    CRITICAL: Uses per-request locking to prevent race conditions.
    When 13 replicas hit this endpoint simultaneously:
    1. First replica acquires lock, others wait
    2. First replica executes LLM, caches result, releases lock
    3. Other 12 replicas get cached result
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        request_id = request.headers.get('X-Request-ID')
        
        if request_id:
            # Fast path: Check cache first (no locking needed for reads)
            cached = icp_cache.get(request_id)
            if cached:
                response, status_code = cached
                return jsonify(response), status_code
            
            # Acquire per-request lock - serializes LLM calls for same request_id
            request_lock = icp_cache.get_request_lock(request_id)
            with request_lock:
                # Double-check cache after acquiring lock (another thread may have cached it)
                cached = icp_cache.get(request_id)
                if cached:
                    response, status_code = cached
                    logger.debug(f'🔄 ICP cache hit after lock for request_id: {request_id}')
                    return jsonify(response), status_code
                
                # Execute the actual function (only one thread per request_id does this)
                result = f(*args, **kwargs)
                
                # Cache the result
                if result:
                    if isinstance(result, tuple):
                        response_data = result[0].get_json()
                        status_code = result[1] if len(result) > 1 else 200
                    else:
                        response_data = result.get_json()
                        status_code = 200
                    
                    icp_cache.set(request_id, response_data, status_code)
                
                return result
        else:
            # No request_id - just execute without caching (direct browser request)
            return f(*args, **kwargs)
    
    return decorated

# ===== API ENDPOINTS =====

@app.route('/health')
def health():
    """
    Health check endpoint for load balancers and monitoring
    
    Returns:
        - status: 'healthy' or 'degraded'
        - provider_id: unique identifier for this provider
        - model: which AI model is loaded
        - gpu_type: hardware type (CPU/GPU)
        - system: CPU and memory usage
        - metrics: performance statistics
        - ollama_connected: whether Ollama is responsive
    """
    ollama_healthy = check_ollama_connection()
    system_info = get_system_info()
    stats = metrics.get_stats()
    
    # Determine overall health
    is_healthy = (
        ollama_healthy and
        metrics.active_requests < MAX_QUEUE_SIZE and
        system_info['memory_percent'] < 95
    )
    
    return jsonify({
        'status': 'healthy' if is_healthy else 'degraded',
        'provider_id': PROVIDER_ID,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        'ollama_connected': ollama_healthy,
        'timestamp': datetime.utcnow().isoformat(),
        'build_timestamp': BUILD_TIMESTAMP,
        'system': system_info,
        'metrics': stats,
        'queue_size': metrics.active_requests,
        'max_queue_size': MAX_QUEUE_SIZE,
    }), 200 if is_healthy else 503


@app.route('/health/icp')
@icp_idempotent
def health_icp():
    """
    Deterministic health check endpoint for ICP HTTP Outcalls.
    
    ICP requires all 13 subnet replicas to receive identical responses
    for consensus. This endpoint returns ONLY static/deterministic data.
    
    Uses @icp_idempotent decorator for X-Request-ID based caching.
    """
    ollama_healthy = check_ollama_connection()
    
    # Only return STATIC values - no timestamps, no dynamic metrics
    return jsonify({
        'status': 'healthy' if ollama_healthy else 'degraded',
        'provider_id': PROVIDER_ID,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        'ollama_connected': ollama_healthy,
        'build_timestamp': BUILD_TIMESTAMP,  # Static - set at startup
        'version': '2.1.0',
        'icp_compatible': True
    }), 200 if ollama_healthy else 503


# ===== FUNDING TRANSPARENCY =====
# Cache for funding data (avoid hammering external APIs)
_funding_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 minute cache
}

# Akash wallet address for the community deployment
AKASH_WALLET_ADDRESS = os.getenv('AKASH_WALLET_ADDRESS', 'akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp')
AKASH_RPC_NODE = os.getenv('AKASH_RPC_NODE', 'https://rpc.akashnet.net:443')

# ICP canister IDs
ICP_BACKEND_CANISTER = os.getenv('ICP_BACKEND_CANISTER', 'au5zq-2qaaa-aaaal-qtowa-cai')
ICP_FRONTEND_CANISTER = os.getenv('ICP_FRONTEND_CANISTER', 'zc67k-kiaaa-aaaal-qtmiq-cai')

# Deployment info (set via YAML env vars during deployment)
DEPLOYMENT_TIER = int(os.getenv('DEPLOYMENT_TIER', '1'))
DEPLOYMENT_TIER_NAME = os.getenv('DEPLOYMENT_TIER_NAME', 'Starter')
HOURLY_COST_AKT = float(os.getenv('HOURLY_COST_AKT', '0.15'))
DAILY_COST_AKT = float(os.getenv('DAILY_COST_AKT', '3.6'))
SESSION_TYPE = os.getenv('SESSION_TYPE', 'community')  # 'community' or 'private'
SESSION_ID = os.getenv('SESSION_ID', '')  # For private sessions
SESSION_EXPIRY = os.getenv('SESSION_EXPIRY', '')  # ISO timestamp for private session end
SESSION_FUNDED_AKT = float(os.getenv('SESSION_FUNDED_AKT', '0'))  # Initial funding amount


def get_akt_price_usd() -> Optional[float]:
    """Fetch current AKT price from CoinGecko API"""
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'akash-network', 'vs_currencies': 'usd'},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('akash-network', {}).get('usd')
    except Exception as e:
        logger.warning(f"Failed to fetch AKT price: {e}")
    return None


# Cache for escrow balance query
_escrow_cache = {'data': None, 'timestamp': 0, 'ttl': 300}  # 5 min cache


def get_escrow_balance() -> Optional[Dict]:
    """
    Query deployment escrow balance from Akash blockchain.
    Returns escrow balance in AKT and calculated time remaining.
    """
    global _escrow_cache
    
    now = time.time()
    
    # Return cached data if fresh
    if _escrow_cache['data'] and (now - _escrow_cache['timestamp']) < _escrow_cache['ttl']:
        return _escrow_cache['data']
    
    try:
        api_url = "https://akash-rest.publicnode.com/akash/escrow/v1beta3/accounts/list"
        params = {
            'filters.owner': AKASH_WALLET_ADDRESS,
            'filters.state': 'open'
        }
        
        response = requests.get(api_url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            accounts = data.get('accounts', [])
            
            if accounts:
                total_uakt = 0
                for account in accounts:
                    balance = account.get('balance', {})
                    total_uakt += int(balance.get('amount', 0))
                
                escrow_akt = total_uakt / 1_000_000
                
                result_data = {
                    'escrow_balance_akt': round(escrow_akt, 4),
                    'active_deployments': len(accounts),
                    'source': 'blockchain'
                }
                
                _escrow_cache['data'] = result_data
                _escrow_cache['timestamp'] = now
                logger.info(f"Fetched escrow balance: {escrow_akt:.4f} AKT from {len(accounts)} deployment(s)")
                return result_data
        else:
            logger.warning(f"Akash escrow API returned status {response.status_code}")
    except requests.exceptions.Timeout:
        logger.warning("Timeout querying Akash escrow balance")
    except Exception as e:
        logger.warning(f"Failed to query escrow balance: {e}")
    
    return None


# Cache for lease price query
_lease_price_cache = {'data': None, 'timestamp': 0, 'ttl': 300}  # 5 min cache

def get_actual_lease_price() -> Optional[Dict]:
    """
    Query actual lease price from Akash blockchain via REST API.
    Returns hourly cost in AKT based on real lease price.
    
    Block time is ~6.5 seconds, so:
    - blocks_per_hour = 3600 / 6.5 ≈ 554
    - hourly_cost_akt = (lease_price_uakt / 1_000_000) * 554
    """
    global _lease_price_cache
    
    now = time.time()
    
    # Return cached data if fresh
    if _lease_price_cache['data'] and (now - _lease_price_cache['timestamp']) < _lease_price_cache['ttl']:
        return _lease_price_cache['data']
    
    try:
        # Use Akash REST API to query leases
        # Working endpoint: https://akash-rest.publicnode.com/akash/market/v1beta5/leases/list
        api_url = "https://akash-rest.publicnode.com/akash/market/v1beta5/leases/list"
        params = {
            'filters.owner': AKASH_WALLET_ADDRESS,
            'filters.state': 'active'
        }
        
        response = requests.get(api_url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            leases = data.get('leases', [])
            
            if leases:
                # Get the most recent active lease (highest dseq)
                latest_lease = max(leases, key=lambda x: int(x.get('lease', {}).get('id', {}).get('dseq', 0)))
                lease = latest_lease.get('lease', {})
                price_uakt = float(lease.get('price', {}).get('amount', 0))
                
                # Calculate hourly rate
                # Block time ≈ 6.5s, so ~554 blocks/hour
                blocks_per_hour = 554
                hourly_akt = (price_uakt / 1_000_000) * blocks_per_hour
                daily_akt = hourly_akt * 24
                
                result_data = {
                    'price_uakt_per_block': price_uakt,
                    'hourly_cost_akt': round(hourly_akt, 4),
                    'daily_cost_akt': round(daily_akt, 2),
                    'dseq': lease.get('id', {}).get('dseq'),
                    'source': 'blockchain'
                }
                
                _lease_price_cache['data'] = result_data
                _lease_price_cache['timestamp'] = now
                logger.info(f"Fetched actual lease price: {hourly_akt:.4f} AKT/hr (${hourly_akt * 0.45:.2f}/hr) from REST API")
                return result_data
        else:
            logger.warning(f"Akash REST API returned status {response.status_code}")
                
    except requests.exceptions.Timeout:
        logger.warning("Timeout querying Akash lease price via REST API")
    except Exception as e:
        logger.warning(f"Failed to query lease price via REST API: {e}")
    
    # Fallback to env var pricing
    return None


def get_akash_deployment_info() -> Dict:
    """
    Get deployment info from environment variables and actual blockchain query.
    Prefers actual lease price from blockchain, falls back to env vars.
    
    For community deployments: uses real lease pricing when available
    For private sessions: includes session ID, expiry time, and remaining balance
    """
    now = time.time()
    
    # Try to get actual lease price from blockchain
    lease_info = get_actual_lease_price()
    
    # Use actual lease price if available, otherwise fall back to env vars
    if lease_info:
        hourly_cost = lease_info['hourly_cost_akt']
        daily_cost = lease_info['daily_cost_akt']
        price_source = 'blockchain'
    else:
        hourly_cost = HOURLY_COST_AKT
        daily_cost = DAILY_COST_AKT
        price_source = 'env_var'
    
    # Base info
    info = {
        'tier': DEPLOYMENT_TIER,
        'tier_name': DEPLOYMENT_TIER_NAME,
        'model': MODEL_NAME,
        'hourly_cost_akt': hourly_cost,
        'daily_cost_akt': daily_cost,
        'price_source': price_source,
        'session_type': SESSION_TYPE,
        'wallet': AKASH_WALLET_ADDRESS,
        'status': 'online'
    }
    
    # For private sessions, calculate time remaining
    if SESSION_TYPE == 'private' and SESSION_EXPIRY:
        try:
            from datetime import datetime
            expiry = datetime.fromisoformat(SESSION_EXPIRY.replace('Z', '+00:00'))
            now_dt = datetime.utcnow().replace(tzinfo=expiry.tzinfo)
            remaining = (expiry - now_dt).total_seconds()
            
            info['session_id'] = SESSION_ID
            info['funded_akt'] = SESSION_FUNDED_AKT
            info['hours_remaining'] = max(0, remaining / 3600)
            info['minutes_remaining'] = max(0, remaining / 60)
            info['expires_at'] = SESSION_EXPIRY
            info['expired'] = remaining <= 0
        except Exception as e:
            logger.warning(f"Failed to parse session expiry: {e}")
            info['hours_remaining'] = 0
            info['expired'] = True
    else:
        # Community deployment - show as "online" without time limit
        info['hours_remaining'] = None  # No limit for community
        info['days_remaining'] = None
    
    return info


@app.route('/funding/status')
def funding_status():
    """
    Funding transparency endpoint.
    Returns current deployment costs, AKT price, and donation addresses.
    Cached for 5 minutes to avoid API rate limits.
    """
    global _funding_cache
    
    now = time.time()
    
    # Return cached data if still fresh
    if _funding_cache['data'] and (now - _funding_cache['timestamp']) < _funding_cache['ttl']:
        return jsonify(_funding_cache['data'])
    
    # Fetch fresh data
    akt_price = get_akt_price_usd()
    akash_info = get_akash_deployment_info()
    escrow_info = get_escrow_balance()
    
    # Add escrow balance and calculate hours remaining
    if escrow_info:
        escrow_akt = escrow_info.get('escrow_balance_akt', 0)
        akash_info['escrow_balance_akt'] = escrow_akt
        akash_info['active_deployments'] = escrow_info.get('active_deployments', 0)
        
        # Calculate hours remaining from escrow ÷ hourly cost
        hourly_cost = akash_info.get('hourly_cost_akt', 0.15)
        if hourly_cost > 0 and escrow_akt > 0:
            hours_remaining = escrow_akt / hourly_cost
            akash_info['hours_remaining'] = round(hours_remaining, 1)
            akash_info['days_remaining'] = round(hours_remaining / 24, 1)
    
    # Calculate USD values if we have AKT price
    if akt_price:
        akash_info['hourly_cost_usd'] = round(akash_info.get('hourly_cost_akt', 0) * akt_price, 4)
        akash_info['daily_cost_usd'] = round(akash_info.get('daily_cost_akt', 0) * akt_price, 2)
        if 'escrow_balance_akt' in akash_info:
            akash_info['escrow_balance_usd'] = round(akash_info['escrow_balance_akt'] * akt_price, 2)
    
    funding_data = {
        'timestamp': int(now * 1000),
        'akt_price_usd': akt_price,
        'akash': akash_info,
        'icp': {
            'backend_canister': ICP_BACKEND_CANISTER,
            'frontend_canister': ICP_FRONTEND_CANISTER,
            'cycles_info': 'Query canister directly for cycle balance'
        },
        'filecoin': {
            'gateway': LIGHTHOUSE_GATEWAY,
            'storage_info': 'Lighthouse free tier: 1GB'
        },
        'donations': {
            'akt_address': AKASH_WALLET_ADDRESS,
            'akt_memo': 'Trinity Community LLM',
            'icp_canister': ICP_BACKEND_CANISTER
        },
        'private_session': {
            'enabled': True,
            'fee_structure': {
                'hardware_percent': 95,
                'platform_percent': 5  # Simplified: 5% goes to platform
            },
            'tiers': [
                {'tier': 1, 'name': 'Starter', 'model': 'tinyllama:1.1b', 'hourly_akt': 0.15, 'ram_gb': 4},
                {'tier': 2, 'name': 'Standard', 'model': 'llama3.1:8b', 'hourly_akt': 0.40, 'ram_gb': 16},
                {'tier': 3, 'name': 'Professional', 'model': 'qwen2.5:72b', 'hourly_akt': 1.75, 'ram_gb': 64}
            ],
            'min_duration_hours': 1,
            'max_duration_hours': 24,
            'payment_address': AKASH_WALLET_ADDRESS
        }
    }
    
    # Update cache
    _funding_cache['data'] = funding_data
    _funding_cache['timestamp'] = now
    
    return jsonify(funding_data)


# ===== PRIVATE SESSION MANAGEMENT =====
@app.route('/session/status')
def session_status():
    """
    Get current session status.
    For private sessions: returns session ID, time remaining, tier info.
    For community sessions: returns community status.
    """
    akash_info = get_akash_deployment_info()
    akt_price = get_akt_price_usd()
    
    if akt_price:
        akash_info['hourly_cost_usd'] = round(akash_info.get('hourly_cost_akt', 0) * akt_price, 4)
    
    return jsonify({
        'session_type': SESSION_TYPE,
        'session_id': SESSION_ID if SESSION_TYPE == 'private' else None,
        'tier': DEPLOYMENT_TIER,
        'tier_name': DEPLOYMENT_TIER_NAME,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        **akash_info,
        'akt_price_usd': akt_price
    })


@app.route('/session/request', methods=['POST'])
def session_request():
    """
    Request a new private session.
    Returns payment instructions (wallet address, memo format, required amount).
    
    Request JSON:
        - tier: 1, 2, or 3
        - hours: duration in hours (1-24)
    
    Response JSON:
        - payment_address: AKT wallet to send payment
        - payment_memo: memo to include in transaction
        - required_akt: amount to send (includes 5% platform fee)
        - required_usd: USD equivalent
        - session_id: unique session identifier
        - expires_in: seconds until payment window closes
    """
    data = request.get_json() or {}
    tier = data.get('tier', 1)
    hours = data.get('hours', 1)
    
    # Validate inputs
    if tier not in [1, 2, 3]:
        return jsonify({'error': 'Invalid tier. Use 1, 2, or 3'}), 400
    
    if hours < 1 or hours > 24:
        return jsonify({'error': 'Hours must be between 1 and 24'}), 400
    
    # Tier pricing
    tier_rates = {1: 0.15, 2: 0.40, 3: 1.75}
    tier_names = {1: 'Starter', 2: 'Standard', 3: 'Professional'}
    tier_models = {1: 'tinyllama:1.1b', 2: 'llama3.1:8b', 3: 'qwen2.5:72b'}
    
    hourly_rate = tier_rates[tier]
    hardware_akt = hourly_rate * hours
    
    # Add 5% platform fee (user pays 105% of hardware cost)
    total_akt = hardware_akt / 0.95
    
    # Get USD price
    akt_price = get_akt_price_usd() or 0.5
    total_usd = round(total_akt * akt_price, 2)
    
    # Generate session ID
    import secrets
    session_id = f"sess_{secrets.token_hex(8)}"
    
    # Payment memo format
    memo = f"trinity:tier:{tier}:{session_id}"
    
    return jsonify({
        'payment_address': AKASH_WALLET_ADDRESS,
        'payment_memo': memo,
        'required_akt': round(total_akt, 4),
        'required_usd': total_usd,
        'hardware_akt': round(hardware_akt, 4),
        'platform_fee_akt': round(total_akt - hardware_akt, 4),
        'session_id': session_id,
        'tier': tier,
        'tier_name': tier_names[tier],
        'model': tier_models[tier],
        'hours': hours,
        'expires_in': 3600,  # 1 hour to complete payment
        'instructions': [
            f"1. Send {round(total_akt, 4)} AKT to {AKASH_WALLET_ADDRESS}",
            f"2. Include memo: {memo}",
            "3. Wait 1-2 minutes for blockchain confirmation",
            "4. Your private LLM will be deployed automatically"
        ]
    })


# Session storage file (created by payment-monitor.py)
ACTIVE_SESSIONS_FILE = '/data/active_sessions.json'


def load_active_sessions() -> Dict:
    """Load active sessions from file."""
    import json
    from pathlib import Path
    
    # Try multiple paths (local dev vs container)
    paths = [
        Path(ACTIVE_SESSIONS_FILE),
        Path(__file__).parent.parent / 'data' / 'active_sessions.json',
        Path.home() / '.trinity' / 'active_sessions.json'
    ]
    
    for path in paths:
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


@app.route('/session/check/<session_id>')
def session_check(session_id: str):
    """
    Check the status of a session by ID.
    
    Returns:
        - status: 'pending' | 'paid' | 'deploying' | 'active' | 'expired' | 'not_found'
        - endpoint: URL for active sessions
        - expires_at: ISO timestamp
        - model: model name
        - tier_name: tier display name
    """
    sessions = load_active_sessions()
    
    if session_id not in sessions:
        return jsonify({
            'session_id': session_id,
            'status': 'pending',  # Payment not yet detected
            'message': 'Waiting for payment confirmation...'
        })
    
    session = sessions[session_id]
    
    # Check if expired
    from datetime import datetime, timezone
    try:
        expiry = datetime.fromisoformat(session.get('expires_at', '').replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        
        if now > expiry:
            return jsonify({
                'session_id': session_id,
                'status': 'expired',
                'expired_at': session.get('expires_at'),
                'message': 'Session has expired'
            })
    except Exception:
        pass
    
    # Check if deployment is complete (has endpoint)
    endpoint = session.get('endpoint') or session.get('uri')
    if endpoint:
        # Ensure URL format
        if not endpoint.startswith('http'):
            endpoint = f"http://{endpoint}"
        
        return jsonify({
            'session_id': session_id,
            'status': 'active',
            'endpoint': endpoint,
            'expires_at': session.get('expires_at'),
            'model': session.get('model'),
            'tier': session.get('tier'),
            'tier_name': session.get('tier_name'),
            'hours': session.get('hours'),
            'dseq': session.get('dseq')
        })
    
    # Payment detected but not yet deployed
    return jsonify({
        'session_id': session_id,
        'status': 'deploying',
        'message': 'Payment confirmed, deploying your private LLM...'
    })


# ===== TRINITY SYSTEM PROMPT =====
# Ultra-minimal prompt - let the model be natural, don't force personality
TRINITY_SYSTEM_PROMPT = """You are a helpful AI assistant. Answer questions directly and concisely."""

# Check if model is "small" (under 8B) - these need simpler prompts
def is_small_model():
    """Small models (TinyLlama, etc.) can't handle complex chat formatting"""
    small_models = ['tinyllama', 'phi', 'gemma:2b', 'stablelm']
    model_lower = MODEL_NAME.lower()
    return any(s in model_lower for s in small_models)


# ===== HELPER FUNCTIONS =====
def build_prompt_with_context(user_prompt: str, context_messages: list, user_memory: Dict = None) -> str:
    """
    Build a prompt that includes Trinity identity, conversation context, and user memory.
    
    For SMALL models (TinyLlama, etc.): Just send the user prompt, no formatting.
    For LARGE models (8B+): Use full chat format with roles.
    
    Args:
        user_prompt: The current user message
        context_messages: Array of recent messages [{ role: 'user'|'assistant'|'system', content: '...' }]
        user_memory: Optional dict with user's persistent memory (facts, preferences)
    
    Returns:
        Full prompt string with context
    """
    # SMALL MODEL PATH: Skip all formatting, just send the question
    # TinyLlama gets confused by [System], User:, Assistant: markers
    if is_small_model():
        logger.info("🔧 Using simple prompt format for small model")
        return user_prompt
    
    # LARGE MODEL PATH: Full chat format (8B+ models handle this correctly)
    conversation_parts = []
    
    # System prompt
    conversation_parts.append(f"[System]\n{TRINITY_SYSTEM_PROMPT}\n")
    
    # Add user memory facts if available (persistent across all chats)
    if user_memory and user_memory.get('facts'):
        facts = user_memory['facts']
        if len(facts) > 0:
            facts_text = "\n".join([f"- {fact['fact']}" for fact in facts[-10:]])  # Last 10 facts
            conversation_parts.append(f"[User Background - Remember these facts]\n{facts_text}\n")
    
    # No context messages case
    if not context_messages or len(context_messages) == 0:
        conversation_parts.append(f"\nUser: {user_prompt}")
        conversation_parts.append(f"\nAssistant:")
        return "\n".join(conversation_parts)
    
    # Build conversation history from context messages
    for msg in context_messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'system':
            conversation_parts.append(f"[Context Summary]\n{content}\n")
        elif role == 'user':
            conversation_parts.append(f"User: {content}")
        elif role == 'assistant':
            conversation_parts.append(f"Assistant: {content}")
    
    conversation_parts.append(f"\nCurrent user message: {user_prompt}")
    conversation_parts.append(f"\nAssistant:")
    
    return "\n".join(conversation_parts)

@app.route('/generate', methods=['POST'])
@icp_idempotent
def generate():
    """
    Generate text using the AI model
    
    Request JSON:
        - prompt: text to generate from (required)
        - max_length: maximum tokens to generate (default: 150)
        - temperature: randomness 0.1-2.0 (default: 0.7)
        - contextMemory: array of recent messages for conversation context (optional)
    
    Response JSON:
        - prompt: the input prompt
        - generated_text: AI-generated text
        - model: which model was used
        - provider_id: which provider generated this
        - gpu_type: hardware used
        - tokens_generated: approximate token count
        - latency_ms: how long it took
    """
    
    # Check if server is at capacity
    if metrics.active_requests >= MAX_QUEUE_SIZE:
        logger.warning(f"Server at capacity: {metrics.active_requests}/{MAX_QUEUE_SIZE}")
        return jsonify({
            'error': 'Server at capacity',
            'queue_size': metrics.active_requests,
            'max_queue_size': MAX_QUEUE_SIZE,
            'provider_id': PROVIDER_ID,
        }), 503
    
    metrics.start_request()
    start_time = time.time()
    
    try:
        # Parse request
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")
        
        user_prompt = data.get('prompt', '')
        max_length = data.get('max_length', 800)  # Default to 800 tokens for longer responses
        context_memory = data.get('contextMemory', [])
        principal = data.get('principal')  # Optional for unauthenticated requests
        document_context = data.get('documentContext')  # Optional attached document
        
        # ICP canister sends options with seed and temperature for deterministic consensus
        options = data.get('options', {})
        temperature = options.get('temperature', data.get('temperature', 0.7))
        seed = options.get('seed')  # ICP deterministic seed - critical for consensus
        
        # Check if this is an ICP request (has X-Request-ID header from canister)
        is_icp_request = request.headers.get('X-Request-ID') is not None
        
        if not user_prompt:
            raise ValueError("Prompt cannot be empty")
        
        # Load user memory if principal provided (for authenticated requests)
        user_memory = None
        if principal:
            try:
                user_memory = load_user_memory(principal)
                if user_memory.get('facts'):
                    logger.info(f"📚 Including {len(user_memory['facts'])} user memory facts")
            except Exception as e:
                logger.warning(f"Could not load user memory: {e}")
        
        # If document context is attached, prepend it to the prompt
        if document_context:
            doc_prefix = f"[Attached Document]\n{document_context[:30000]}\n[End Document]\n\nBased on the above document, "
            user_prompt = doc_prefix + user_prompt
            logger.info(f"📄 Document attached: {len(document_context)} chars")
        
        # Build prompt with context and user memory
        full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)
        
        # Privacy: Log word count and hash only - don't expose prompt content
        import hashlib
        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:8]
        word_count = len(user_prompt.split())
        context_count = len(context_memory)
        
        # Single consolidated log line for request
        logger.info(f"🤖 Request: {word_count} words (#{prompt_hash}), {context_count} ctx, seed={seed}")
        
        # Generate with Ollama
        # Build Ollama options
        ollama_options = {
            "num_predict": max_length,
            "temperature": temperature,
        }
        
        # Add seed for deterministic generation (critical for ICP consensus)
        # When seed is set, all 13 ICP replicas get identical LLM output
        if seed is not None:
            ollama_options["seed"] = int(seed)
            logger.info(f"🎲 Using deterministic seed: {seed}")
        
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": full_prompt,
                "stream": False,
                "options": ollama_options
            },
            timeout=300  # 5 minutes for large models like Qwen 72B
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama returned status {response.status_code}")
        
        result = response.json()
        generated_text = result.get('response', '')
        tokens_generated = len(generated_text.split())  # Rough approximation
        
        # Calculate metrics
        latency_ms = (time.time() - start_time) * 1000
        tokens_generated = len(generated_text.split())  # Rough approximation
        
        # Record success
        metrics.record_request(True, tokens_generated, latency_ms)
        
        logger.info(f"[{PROVIDER_ID}] Generated {tokens_generated} tokens in {latency_ms:.0f}ms")
        
        # Build response - ICP requests get deterministic fields only for consensus
        response_data = {
            'response': generated_text,  # Match Rust GenerateResponse struct
            'model': MODEL_NAME,
            'provider_id': PROVIDER_ID,
            'done': True,
        }
        
        # Only include non-deterministic fields for non-ICP requests
        # ICP runs 13 replicas - they must all get identical responses
        if not is_icp_request:
            response_data['prompt'] = user_prompt
            response_data['generated_text'] = generated_text
            response_data['gpu_type'] = GPU_TYPE
            response_data['tokens_generated'] = tokens_generated
            response_data['latency_ms'] = latency_ms
            response_data['timestamp'] = datetime.utcnow().isoformat()
        
        return jsonify(response_data)
        
    except ValueError as e:
        metrics.record_request(False, 0, 0)
        logger.warning(f"Validation error: {e}")
        return jsonify({'error': str(e), 'provider_id': PROVIDER_ID}), 400
        
    except requests.Timeout:
        metrics.record_request(False, 0, 0)
        logger.error("Ollama request timed out")
        return jsonify({'error': 'Request timeout', 'provider_id': PROVIDER_ID}), 504
        
    except Exception as e:
        metrics.record_request(False, 0, 0)
        logger.error(f"Generation error: {e}", exc_info=True)
        return jsonify({
            'error': f'Generation failed: {str(e)}',
            'provider_id': PROVIDER_ID
        }), 500
        
    finally:
        metrics.end_request()


# ============================================================================
# SIMPLE GENERATE ENDPOINT (Minimal, no decorators, no context building)
# ============================================================================

@app.route('/generate/simple', methods=['POST'])
def generate_simple():
    """
    Ultra-minimal generate endpoint for testing and debugging.
    No auth, no context, no user memory, no metrics - just prompt → Ollama → response.
    
    Request JSON:
        - prompt: text to generate from (required)
        - max_length: max tokens (default: 200)
        - temperature: 0.1-2.0 (default: 0.7)
    
    Response JSON:
        - response: AI-generated text
        - model: model name
        - ok: true/false
    """
    try:
        data = request.json or {}
        prompt = data.get('prompt', '').strip()
        
        if not prompt:
            return jsonify({'ok': False, 'error': 'No prompt provided'}), 400
        
        max_length = min(data.get('max_length', 150), 300)  # Cap at 300 tokens
        temperature = data.get('temperature', 0.7)
        
        # Add minimal framing to prevent hallucination (TinyLlama needs guidance)
        framed_prompt = f"User: {prompt}\n\nAssistant:"
        
        # Direct Ollama call - nothing fancy
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": framed_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_length,
                    "temperature": temperature,
                    "stop": ["User:", "\n\nUser"]  # Stop before hallucinating next turn
                }
            },
            timeout=120
        )
        
        if response.status_code != 200:
            return jsonify({'ok': False, 'error': f'Ollama error: {response.status_code}'}), 500
        
        result = response.json()
        return jsonify({
            'ok': True,
            'response': result.get('response', ''),
            'model': MODEL_NAME
        })
        
    except Exception as e:
        logger.error(f"Simple generate error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/generate/simple/stream', methods=['POST'])
def generate_simple_stream():
    """
    Ultra-minimal streaming generate endpoint.
    No auth, no context - just prompt → Ollama stream → SSE response.
    """
    try:
        data = request.json or {}
        prompt = data.get('prompt', '').strip()
        
        if not prompt:
            return jsonify({'ok': False, 'error': 'No prompt provided'}), 400
        
        max_length = min(data.get('max_length', 150), 300)  # Cap at 300
        temperature = data.get('temperature', 0.7)
        
        # Add minimal framing (TinyLlama needs guidance)
        framed_prompt = f"User: {prompt}\n\nAssistant:"
        
        def stream_response():
            try:
                response = requests.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": MODEL_NAME,
                        "prompt": framed_prompt,
                        "stream": True,
                        "options": {
                            "num_predict": max_length,
                            "temperature": temperature,
                            "stop": ["User:", "\n\nUser"]  # Stop before hallucinating
                        }
                    },
                    stream=True,
                    timeout=120
                )
                
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get('response', '')
                            if token:
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            if chunk.get('done'):
                                yield f"data: {json.dumps({'done': True})}\n\n"
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(
            stream_response(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
    except Exception as e:
        logger.error(f"Simple stream error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


# ============================================================================
# STREAMING GENERATE ENDPOINT
# ============================================================================

@app.route('/generate/stream', methods=['POST'])
def generate_stream():
    """
    Generate text using AI model with Server-Sent Events (SSE) streaming.
    Tokens are sent as they're generated for real-time display.
    
    Request JSON: Same as /generate
    Response: SSE stream with data: {"token": "..."} events
    """
    from flask import Response, stream_with_context
    
    # Check capacity
    if metrics.active_requests >= MAX_QUEUE_SIZE:
        return jsonify({'error': 'Server at capacity'}), 503
    
    metrics.start_request()
    
    try:
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")
        
        user_prompt = data.get('prompt', '')
        max_length = data.get('max_length', 800)
        context_memory = data.get('contextMemory', [])
        principal = data.get('principal')
        document_context = data.get('documentContext')
        temperature = data.get('temperature', 0.7)
        
        # Load user memory if principal provided
        user_memory = None
        if principal:
            try:
                user_memory = load_user_memory(principal)
            except Exception:
                pass
        
        # Prepend document context if attached
        if document_context:
            doc_prefix = f"[Attached Document]\n{document_context[:30000]}\n[End Document]\n\nBased on the above document, "
            user_prompt = doc_prefix + user_prompt
        
        # Build full prompt
        full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)
        
        logger.info(f"🌊 Streaming request: {len(user_prompt.split())} words, {len(context_memory)} ctx")
        
        def generate_sse():
            """Generator that yields SSE-formatted chunks"""
            try:
                # Call Ollama with streaming enabled
                response = requests.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": MODEL_NAME,
                        "prompt": full_prompt,
                        "stream": True,
                        "options": {
                            "num_predict": max_length,
                            "temperature": temperature,
                        }
                    },
                    stream=True,
                    timeout=300
                )
                
                if response.status_code != 200:
                    yield f"data: {json.dumps({'error': 'Ollama error'})}\n\n"
                    return
                
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get('response', '')
                            full_response += token
                            
                            # Send token to client
                            yield f"data: {json.dumps({'token': token})}\n\n"
                            
                            # Check if done
                            if chunk.get('done', False):
                                yield f"data: {json.dumps({'done': True, 'model': MODEL_NAME})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
                
                metrics.record_request(True, len(full_response.split()), 0)
                
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                metrics.end_request()
        
        return Response(
            stream_with_context(generate_sse()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',  # Disable nginx buffering
            }
        )
        
    except Exception as e:
        metrics.end_request()
        logger.error(f"Stream setup error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# NEW ENDPOINTS: CHAT PERSISTENCE & ARCHIVE
# ============================================================================

@app.route('/chat/autosave', methods=['POST'])
@require_auth
def autosave_chat():
    """Save chat after each message exchange - syncs to both local disk AND Lighthouse (IPFS/Filecoin)"""
    try:
        # Principal is set by @require_auth decorator
        principal = request.principal
        data = request.json
        
        # Privacy: Only log request metadata, not content
        logger.debug(f'📥 Autosave request from {principal[:16]}...')
        
        chat_id = data.get('chatId')
        messages = data.get('messages', [])
        metadata = data.get('metadata', {})
        
        # Privacy: Don't log metadata (may contain user-generated titles)
        logger.debug(f'   chatId: {chat_id}, messages: {len(messages)}')
        
        if not chat_id:
            logger.error('❌ Missing chatId in autosave request')
            return jsonify({'error': 'Missing chatId'}), 400
        
        # Prepare chat data for encryption
        chat_data = {
            'chatId': chat_id,
            'messages': messages,
            'metadata': metadata,
            'principal': principal,  # Include for verification on restore
            'savedAt': int(time.time() * 1000)
        }
        
        # Encrypt content
        encrypted = EncryptionUtils.encrypt_chat(chat_data, principal)
        encrypted_json = json.dumps(encrypted)
        
        # Save to local disk (fast, but ephemeral on Akash redeploy)
        chat_filename = f"{chat_id}.json"
        chat_path = get_user_dir(principal) / chat_filename
        
        with open(chat_path, 'w') as f:
            f.write(encrypted_json)
        
        # ==========================================
        # SYNC TO LIGHTHOUSE (IPFS + FILECOIN)
        # This ensures data survives Akash redeployments
        # ==========================================
        cid = None
        try:
            # Upload encrypted chat to Lighthouse
            lighthouse_filename = f"{principal[:16]}_{chat_id}.json"
            cid = upload_to_filecoin(
                encrypted_json.encode('utf-8'),
                lighthouse_filename,
                principal_id=principal
            )
            if cid:
                logger.info(f'☁️  Synced to IPFS: {cid[:16]}...')
        except Exception as sync_error:
            # Don't fail the autosave if Lighthouse sync fails
            logger.warning(f'⚠️  Lighthouse sync failed (local save OK): {sync_error}')
        
        # Update metadata with CID for later retrieval
        user_metadata = load_metadata(principal)
        
        # Find or create chat entry in metadata
        chat_entry = next((c for c in user_metadata['chats'] if c['chatId'] == chat_id), None)
        if not chat_entry:
            chat_entry = {
                'chatId': chat_id,
                'title': metadata.get('title', 'Untitled'),
                'createdAt': int(time.time() * 1000),
                'isArchived': False
            }
            user_metadata['chats'].append(chat_entry)
        
        chat_entry['lastUpdated'] = metadata.get('updatedAt', int(time.time() * 1000))
        chat_entry['messageCount'] = len(messages)
        if cid:
            chat_entry['cid'] = cid  # Store CID for retrieval after redeploy
        
        save_metadata(principal, user_metadata)
        
        # Also sync metadata to Lighthouse (so we can restore chat list)
        try:
            metadata_filename = f"{principal[:16]}_metadata.json"
            metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
            upload_to_filecoin(
                json.dumps(metadata_encrypted).encode('utf-8'),
                metadata_filename,
                principal_id=principal,
                is_master_bundle=True
            )
        except Exception as meta_sync_error:
            logger.warning(f'⚠️  Metadata sync failed: {meta_sync_error}')
        
        # Privacy: Single minimal log line for successful autosave
        logger.info(f'💾 Autosaved chat {chat_id[:8]}... ({len(messages)} msgs)')
        
        return jsonify({
            'success': True,
            'chatId': chat_id,
            'savedAt': int(time.time() * 1000),
            'cid': cid,  # Return CID to frontend
            'nextAutoDeleteAt': int(time.time() * 1000) + (7 * 24 * 60 * 60 * 1000)
        })
    
    except Exception as e:
        logger.error(f'❌ Autosave error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat/list', methods=['GET'])
@require_auth
def list_chats():
    """List all chats for user - merges local metadata with Lighthouse recovery"""
    try:
        principal = request.principal
        user_metadata = load_metadata(principal)
        local_chats = user_metadata.get('chats', [])
        
        # ==========================================
        # RECOVER FROM LIGHTHOUSE IF LOCAL IS EMPTY
        # This restores user's chat list after Akash redeploy
        # ==========================================
        if not local_chats:
            logger.info(f'🔍 No local chats, attempting Lighthouse recovery for {principal[:16]}...')
            try:
                # Look for user's metadata bundle in Lighthouse
                uploads = get_lighthouse_uploads(principal)
                metadata_cid = None
                
                for upload in uploads:
                    filename = upload.get('fileName', '')
                    if principal[:16] in filename and 'metadata' in filename:
                        metadata_cid = upload.get('cid')
                        break
                
                if metadata_cid:
                    logger.info(f'☁️  Found metadata on IPFS: {metadata_cid[:16]}...')
                    gateway_url = f'{LIGHTHOUSE_GATEWAY}/ipfs/{metadata_cid}'
                    response = requests.get(gateway_url, timeout=30)
                    
                    if response.status_code == 200:
                        encrypted_metadata = response.json()
                        recovered_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)
                        
                        # Merge recovered chats
                        local_chats = recovered_metadata.get('chats', [])
                        user_metadata['chats'] = local_chats
                        save_metadata(principal, user_metadata)
                        logger.info(f'✅ Recovered {len(local_chats)} chats from IPFS')
                else:
                    # No metadata bundle, but check for individual chat files
                    recovered = []
                    for upload in uploads[:50]:  # Limit to recent 50
                        filename = upload.get('fileName', '')
                        if principal[:16] in filename and 'metadata' not in filename:
                            # Extract chat_id from filename pattern: principal_chatId.json
                            parts = filename.replace('.json', '').split('_')
                            if len(parts) >= 2:
                                chat_id = parts[-1]
                                recovered.append({
                                    'chatId': chat_id,
                                    'title': 'Recovered Chat',
                                    'cid': upload.get('cid'),
                                    'lastUpdated': upload.get('createdAt', 0),
                                    'isArchived': False
                                })
                    if recovered:
                        local_chats = recovered
                        user_metadata['chats'] = local_chats
                        save_metadata(principal, user_metadata)
                        logger.info(f'✅ Recovered {len(recovered)} chats from individual IPFS files')
                        
            except Exception as recovery_error:
                logger.warning(f'⚠️  Lighthouse recovery failed: {recovery_error}')
        
        # Sort by last updated (newest first)
        local_chats.sort(key=lambda x: x.get('lastUpdated', 0), reverse=True)
        
        return jsonify({
            'chats': local_chats,
            'count': len(local_chats)
        })
    
    except Exception as e:
        logger.error(f'List chats error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<chat_id>', methods=['GET'])
@require_auth
def get_chat(chat_id):
    """Load specific chat - tries local disk first, then falls back to Lighthouse (IPFS)"""
    try:
        principal = request.principal
        chat_path = get_user_dir(principal) / f"{chat_id}.json"
        
        # Try local disk first (fastest)
        if chat_path.exists():
            logger.debug(f'📂 Loading chat from local disk: {chat_id[:8]}...')
            with open(chat_path, 'r') as f:
                encrypted_data = json.load(f)
            decrypted = EncryptionUtils.decrypt_chat(encrypted_data, principal)
            return jsonify(decrypted)
        
        # ==========================================
        # FALLBACK TO LIGHTHOUSE (IPFS)
        # This recovers data after Akash redeployments
        # ==========================================
        logger.info(f'🔍 Chat not on local disk, checking Lighthouse: {chat_id[:8]}...')
        
        # Check if we have a CID stored for this chat
        user_metadata = load_metadata(principal)
        chat_entry = next((c for c in user_metadata.get('chats', []) if c['chatId'] == chat_id), None)
        
        cid = None
        if chat_entry and chat_entry.get('cid'):
            cid = chat_entry['cid']
        else:
            # Try to find CID by filename pattern in Lighthouse
            try:
                uploads = get_lighthouse_uploads(principal)
                for upload in uploads:
                    filename = upload.get('fileName', '')
                    if chat_id in filename:
                        cid = upload.get('cid')
                        break
            except Exception as e:
                logger.warning(f'Could not search Lighthouse uploads: {e}')
        
        if cid:
            logger.info(f'☁️  Found CID: {cid[:16]}..., downloading from IPFS')
            try:
                # Download from Lighthouse gateway
                gateway_url = f'{LIGHTHOUSE_GATEWAY}/ipfs/{cid}'
                response = requests.get(gateway_url, timeout=30)
                
                if response.status_code == 200:
                    encrypted_data = response.json()
                    decrypted = EncryptionUtils.decrypt_chat(encrypted_data, principal)
                    
                    # Cache locally for next time
                    chat_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(chat_path, 'w') as f:
                        json.dump(encrypted_data, f)
                    logger.info(f'✅ Restored from IPFS and cached locally: {chat_id[:8]}...')
                    
                    return jsonify(decrypted)
                else:
                    logger.warning(f'IPFS gateway returned {response.status_code}')
            except Exception as ipfs_error:
                logger.error(f'Failed to download from IPFS: {ipfs_error}')
        
        return jsonify({'error': 'Chat not found (not on disk or IPFS)'}), 404
    
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        logger.error(f'Get chat error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<chat_id>', methods=['DELETE'])
@require_auth
def delete_chat(chat_id):
    """Delete chat"""
    try:
        principal = request.principal
        chat_path = get_user_dir(principal) / f"{chat_id}.json"
        
        if chat_path.exists():
            chat_path.unlink()
        
        # Remove from metadata
        user_metadata = load_metadata(principal)
        user_metadata['chats'] = [c for c in user_metadata['chats'] if c['chatId'] != chat_id]
        save_metadata(principal, user_metadata)
        
        logger.info(f'Chat deleted: {chat_id} for {principal}')
        
        return jsonify({
            'success': True,
            'deletedAt': int(time.time() * 1000)
        })
    
    except Exception as e:
        logger.error(f'Delete chat error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<chat_id>/archive', methods=['POST'])
@require_auth
def archive_chat(chat_id):
    """Archive chat to Pinata/Filecoin with immediate upload"""
    try:
        principal = request.principal
        chat_path = get_user_dir(principal) / f"{chat_id}.json"

        if not chat_path.exists():
            return jsonify({'error': 'Chat not found'}), 404

        # Load metadata
        user_metadata = load_metadata(principal)
        chat_entry = next((c for c in user_metadata['chats'] if c['chatId'] == chat_id), None)

        if not chat_entry:
            return jsonify({'error': 'Chat not found in metadata'}), 404

        # Check if already archived
        if chat_entry.get('isArchived'):
            return jsonify({'error': 'Chat is already archived'}), 400

        # Hard limit: Maximum 10 archived chats
        archived_count = sum(1 for c in user_metadata['chats'] if c.get('isArchived', False))
        if archived_count >= 10:
            return jsonify({
                'error': 'Maximum 10 archived chats reached. Please delete an archived chat first.',
                'limit': 10,
                'current': archived_count
            }), 400

        # Load the encrypted chat file
        with open(chat_path, 'r') as f:
            encrypted_chat = json.load(f)

        # Upload to Pinata with principal metadata tagging
        logger.info(f'📤 Uploading chat {chat_id} to Pinata...')
        chat_filename = f"{principal[:20]}_{chat_id}.json"
        chat_data_bytes = json.dumps(encrypted_chat).encode('utf-8')

        cid = upload_to_filecoin(chat_data_bytes, chat_filename, principal_id=principal, is_master_bundle=False)

        if not cid:
            return jsonify({
                'error': 'Failed to upload to Filecoin - check API key configuration',
                'lighthouse_configured': bool(LIGHTHOUSE_API_KEY)
            }), 500

        # Update metadata with CID and archive status
        chat_entry['isArchived'] = True
        chat_entry['archivedAt'] = int(time.time() * 1000)
        chat_entry['filecoinCID'] = cid

        save_metadata(principal, user_metadata)

        logger.info(f'✅ Chat archived to Filecoin: {chat_id} -> CID: {cid}')

        # Update master bundle (Phase B)
        bundle_cid = update_master_bundle(principal, user_metadata)

        return jsonify({
            'success': True,
            'chatId': chat_id,
            'cid': cid,
            'masterBundleCID': bundle_cid,
            'archivedAt': chat_entry['archivedAt'],
            'archivedCount': archived_count + 1
        })

    except Exception as e:
        logger.error(f'❌ Archive error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


def update_master_bundle(principal_id: str, user_metadata: Dict = None) -> Optional[str]:
    """
    Create/update master bundle containing index of all archived chats.
    This is the single CID that gives access to all user's archives.

    Args:
        principal_id: User's principal ID
        user_metadata: Optional pre-loaded metadata (loads if not provided)

    Returns:
        New master bundle CID on success, None on failure
    """
    try:
        if user_metadata is None:
            user_metadata = load_metadata(principal_id)

        # Build manifest of all archived chats
        archived_chats = [
            {
                'chatId': c['chatId'],
                'title': c.get('title', 'Untitled'),
                'cid': c.get('filecoinCID'),
                'archivedAt': c.get('archivedAt'),
                'messageCount': c.get('messageCount', 0)
            }
            for c in user_metadata.get('chats', [])
            if c.get('isArchived') and c.get('filecoinCID')
        ]

        if not archived_chats:
            logger.info(f'No archived chats with CIDs for {principal_id[:20]}...')
            return None

        # Create master bundle manifest
        manifest = {
            'version': '1.0',
            'type': 'master_bundle',
            'principal': principal_id,
            'createdAt': int(time.time() * 1000),
            'bundleVersion': user_metadata.get('lastBundleVersion', 0) + 1,
            'chats': archived_chats,
            'chatCount': len(archived_chats)
        }

        # Encrypt manifest with principal ID
        encrypted_manifest = EncryptionUtils.encrypt_chat(manifest, principal_id)

        # Upload master bundle to Pinata
        bundle_filename = f"{principal_id[:20]}_master_bundle.json"
        bundle_data = json.dumps(encrypted_manifest).encode('utf-8')

        bundle_cid = upload_to_filecoin(bundle_data, bundle_filename, principal_id=principal_id, is_master_bundle=True)

        if bundle_cid:
            # Update local metadata with new bundle CID
            user_metadata['currentBundleCID'] = bundle_cid
            user_metadata['lastBundleVersion'] = manifest['bundleVersion']
            user_metadata['lastSyncedAt'] = int(time.time() * 1000)
            save_metadata(principal_id, user_metadata)

            logger.info(f'✅ Master bundle updated: {bundle_cid} (v{manifest["bundleVersion"]}, {len(archived_chats)} chats)')

        return bundle_cid

    except Exception as e:
        logger.error(f'❌ Master bundle update error: {e}', exc_info=True)
        return None


# ===== ARCHIVE RECOVERY ENDPOINTS =====

@app.route('/chat/recover-archives', methods=['GET'])
@require_auth
def recover_archives():
    """
    Recover all archived chats for the authenticated user.
    Searches Pinata for the user's master bundle, downloads and decrypts it.

    Returns:
        List of archived chat metadata with CIDs for individual download
    """
    try:
        principal = request.principal
        logger.info(f'🔍 Recovering archives for {principal[:20]}...')

        # First check local metadata for known bundle CID
        user_metadata = load_metadata(principal)
        local_bundle_cid = user_metadata.get('currentBundleCID')

        # Note: Lighthouse doesn't support metadata search like Pinata
        # We rely on local metadata for bundle CID tracking
        # The get_lighthouse_uploads function returns all files for this API key
        uploads = get_lighthouse_uploads(principal_id=principal)

        if not uploads and not local_bundle_cid:
            return jsonify({
                'success': True,
                'message': 'No archived chats found',
                'archives': [],
                'count': 0
            })

        # Use the local bundle CID (Lighthouse doesn't have per-user metadata)
        bundle_cid = local_bundle_cid

        if not bundle_cid:
            return jsonify({
                'success': True,
                'message': 'No master bundle found',
                'archives': [],
                'count': 0
            })

        logger.info(f'📥 Downloading master bundle: {bundle_cid}')

        # Download master bundle from IPFS
        bundle_data = download_from_filecoin(bundle_cid)

        if not bundle_data:
            return jsonify({
                'error': 'Failed to download master bundle from IPFS',
                'cid': bundle_cid
            }), 500

        # Parse and decrypt master bundle
        encrypted_manifest = json.loads(bundle_data.decode('utf-8'))
        manifest = EncryptionUtils.decrypt_chat(encrypted_manifest, principal)

        logger.info(f'✅ Recovered {manifest.get("chatCount", 0)} archived chats')

        return jsonify({
            'success': True,
            'masterBundleCID': bundle_cid,
            'bundleVersion': manifest.get('bundleVersion', 0),
            'archives': manifest.get('chats', []),
            'count': manifest.get('chatCount', 0),
            'recoveredAt': int(time.time() * 1000)
        })

    except ValueError as e:
        logger.error(f'Decryption failed during recovery: {e}')
        return jsonify({'error': 'Failed to decrypt archives - wrong principal?'}), 401
    except Exception as e:
        logger.error(f'❌ Archive recovery error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/chat/archive/<cid>', methods=['GET'])
@require_auth
def get_archived_chat(cid):
    """
    Download and decrypt a specific archived chat by its CID.

    Args:
        cid: The IPFS CID of the archived chat

    Returns:
        Decrypted chat data
    """
    try:
        principal = request.principal
        logger.info(f'📥 Downloading archived chat: {cid}')

        # Download from IPFS
        chat_data = download_from_filecoin(cid)

        if not chat_data:
            return jsonify({
                'error': 'Failed to download chat from IPFS',
                'cid': cid
            }), 404

        # Parse and decrypt
        encrypted_chat = json.loads(chat_data.decode('utf-8'))
        decrypted_chat = EncryptionUtils.decrypt_chat(encrypted_chat, principal)

        logger.info(f'✅ Archived chat recovered: {cid}')

        return jsonify({
            'success': True,
            'cid': cid,
            'chat': decrypted_chat,
            'recoveredAt': int(time.time() * 1000)
        })

    except ValueError as e:
        logger.error(f'Decryption failed: {e}')
        return jsonify({'error': 'Failed to decrypt chat - wrong principal?'}), 401
    except Exception as e:
        logger.error(f'❌ Archive download error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/chat/archive/status/<cid>', methods=['GET'])
def get_archive_deal_status(cid):
    """
    Check Filecoin deal status for an archived chat.
    
    Filecoin deals typically take 1-24 hours to be created after upload.
    This endpoint allows checking if the content has been sealed on Filecoin.
    
    No auth required - CID is public, status is public information.
    
    Args:
        cid: The IPFS CID to check
        
    Returns:
        Deal status information including:
        - status: 'pending', 'active', 'error'
        - message: Human-readable status
        - deals: Array of Filecoin deal information (if active)
    """
    try:
        logger.info(f'📊 Checking Filecoin deal status for: {cid}')
        
        status = get_filecoin_deal_status(cid)
        
        return jsonify({
            'cid': cid,
            'filecoin': status,
            'gateways': [
                f'{LIGHTHOUSE_GATEWAY}/ipfs/{cid}',
                f'https://ipfs.io/ipfs/{cid}',
                f'https://dweb.link/ipfs/{cid}'
            ],
            'checkedAt': int(time.time() * 1000)
        })
        
    except Exception as e:
        logger.error(f'❌ Deal status check error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ===== USER MEMORY ENDPOINTS =====
@app.route('/user/memory', methods=['GET'])
@require_auth
def get_user_memory():
    """Get user's persistent memory (facts, preferences)"""
    try:
        principal = request.principal
        memory = load_user_memory(principal)
        
        logger.debug(f'📖 Loaded user memory: {len(memory.get("facts", []))} facts')
        return jsonify(memory)
    
    except Exception as e:
        logger.error(f'❌ Error loading user memory: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/user/memory', methods=['POST'])
@require_auth
def update_user_memory():
    """Update user's persistent memory"""
    try:
        principal = request.principal
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        memory = load_user_memory(principal)
        
        # Update facts if provided
        if 'facts' in data:
            memory['facts'] = data['facts']
        
        # Update preferences if provided
        if 'preferences' in data:
            memory['preferences'] = data['preferences']
        
        save_user_memory(principal, memory)
        
        logger.debug(f'💾 Updated user memory')
        return jsonify({
            'success': True,
            'memory': memory
        })
    
    except Exception as e:
        logger.error(f'❌ Error updating user memory: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/user/memory/fact', methods=['POST'])
@require_auth
def add_memory_fact():
    """Add a single fact to user's memory"""
    try:
        principal = request.principal
        data = request.json
        
        if not data or 'fact' not in data:
            return jsonify({'error': 'Fact is required'}), 400
        
        memory = load_user_memory(principal)
        
        new_fact = {
            'fact': data['fact'],
            'addedAt': int(time.time() * 1000),
            'fromChatId': data.get('chatId'),
            'category': data.get('category', 'general')
        }
        
        memory['facts'].append(new_fact)
        save_user_memory(principal, memory)
        
        logger.info(f'➕ Added fact to user memory (total: {len(memory["facts"])})')
        return jsonify({
            'success': True,
            'fact': new_fact,
            'totalFacts': len(memory['facts'])
        })
    
    except Exception as e:
        logger.error(f'❌ Error adding memory fact: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/user/memory/fact/<int:index>', methods=['DELETE'])
@require_auth
def delete_memory_fact(index):
    """Delete a fact from user's memory"""
    try:
        principal = request.principal
        memory = load_user_memory(principal)
        
        if index < 0 or index >= len(memory['facts']):
            return jsonify({'error': 'Invalid fact index'}), 400
        
        deleted_fact = memory['facts'].pop(index)
        save_user_memory(principal, memory)
        
        logger.info(f'🗑️ Deleted fact #{index} from user memory (remaining: {len(memory["facts"])})')
        return jsonify({
            'success': True,
            'deletedFact': deleted_fact,
            'totalFacts': len(memory['facts'])
        })
    
    except Exception as e:
        logger.error(f'❌ Error deleting memory fact: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# AI TOOLS ENDPOINTS (Using Ollama/Llama3)
# ============================================================================

def call_ollama_for_tools(prompt: str, temperature: float = 0.7) -> str:
    """Helper function to call Ollama API for tools."""
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature}
            },
            timeout=300  # 5 minutes for large models
        )
        response.raise_for_status()
        return response.json().get('response', '')
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        raise


# ----- CHAT WITH DOCUMENTS -----

@app.route('/tools/documents/upload', methods=['POST'])
def upload_document():
    """Upload a document for querying."""
    try:
        data = request.json
        content = data.get('content', '')
        filename = data.get('filename', 'uploaded_document.txt')
        session_id = data.get('sessionId', str(time.time()))

        if not content:
            return jsonify({'error': 'No content provided'}), 400

        document_store[session_id] = {
            'content': content,
            'filename': filename,
            'uploaded_at': datetime.utcnow().isoformat()
        }

        logger.info(f'📄 Document uploaded: {filename} ({len(content)} chars)')
        return jsonify({
            'success': True,
            'sessionId': session_id,
            'filename': filename,
            'documentLength': len(content)
        })
    except Exception as e:
        logger.error(f'❌ Document upload error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/tools/documents/query', methods=['POST'])
def query_document():
    """Query an uploaded document using Ollama."""
    try:
        data = request.json
        session_id = data.get('sessionId', '')
        query = data.get('query', '')

        if not session_id or session_id not in document_store:
            return jsonify({'error': 'No document found. Please upload first.'}), 400
        if not query:
            return jsonify({'error': 'No query provided'}), 400

        doc = document_store[session_id]
        doc_content = doc['content'][:30000]

        prompt = f"""You are a helpful document analysis assistant.
Answer based ONLY on this document. If not found, say so.

=== DOCUMENT ({doc['filename']}) ===
{doc_content}
=== END DOCUMENT ===

Question: {query}
Answer:"""

        answer = call_ollama_for_tools(prompt, temperature=0.3)
        logger.info(f'📄 Document query: "{query[:50]}..."')
        return jsonify({'answer': answer, 'documentUsed': doc['filename'], 'model': MODEL_NAME})
    except Exception as e:
        logger.error(f'❌ Document query error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ----- TRANSCRIPT CLEANER -----

@app.route('/tools/transcript/clean', methods=['POST'])
def clean_transcript():
    """Clean and polish a transcript."""
    try:
        data = request.json
        raw_text = data.get('text', '')

        if not raw_text:
            return jsonify({'error': 'No text provided'}), 400

        prompt = f"""You are a professional transcript editor. Clean this transcript:
1. Fix grammar, spelling, punctuation
2. Remove filler words (um, uh, like) unless meaningful
3. Fix run-on sentences
4. Preserve speaker labels if present
5. Maintain original meaning and tone

Return ONLY the cleaned transcript.

=== RAW TRANSCRIPT ===
{raw_text}
=== END ===

Cleaned transcript:"""

        cleaned = call_ollama_for_tools(prompt, temperature=0.3)
        logger.info(f'🎙️ Transcript cleaned: {len(raw_text)} -> {len(cleaned)} chars')
        return jsonify({
            'cleanedText': cleaned,
            'originalLength': len(raw_text),
            'cleanedLength': len(cleaned),
            'model': MODEL_NAME
        })
    except Exception as e:
        logger.error(f'❌ Transcript error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ----- AUDIO TRANSCRIPTION -----

# File size limit: 25MB (Whisper works best with files under this size)
MAX_AUDIO_SIZE_MB = 25
MAX_AUDIO_SIZE_BYTES = MAX_AUDIO_SIZE_MB * 1024 * 1024

@app.route('/tools/audio/transcribe', methods=['POST'])
def transcribe_audio():
    """Transcribe audio file using Whisper."""
    global WHISPER_MODEL
    
    if not WHISPER_AVAILABLE:
        return jsonify({'error': 'Whisper not available on this server'}), 503
    
    try:
        # Check if file was uploaded
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file size
        audio_file.seek(0, 2)  # Seek to end
        file_size = audio_file.tell()
        audio_file.seek(0)  # Seek back to start
        
        if file_size > MAX_AUDIO_SIZE_BYTES:
            return jsonify({
                'error': f'File too large. Maximum size is {MAX_AUDIO_SIZE_MB}MB',
                'fileSize': file_size,
                'maxSize': MAX_AUDIO_SIZE_BYTES
            }), 413
        
        # Lazy load Whisper model (base model is fast and good enough)
        if WHISPER_MODEL is None:
            logger.info('🎤 Loading Whisper model (first use)...')
            WHISPER_MODEL = whisper.load_model('base')
            logger.info('✅ Whisper model loaded')
        
        # Save to temp file (Whisper needs a file path)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Transcribe
            logger.info(f'🎤 Transcribing audio: {audio_file.filename} ({file_size / 1024:.1f}KB)')
            result = WHISPER_MODEL.transcribe(tmp_path)
            transcript = result['text'].strip()
            
            logger.info(f'✅ Transcription complete: {len(transcript)} chars')
            return jsonify({
                'transcript': transcript,
                'language': result.get('language', 'unknown'),
                'duration': result.get('duration', 0),
                'fileSize': file_size,
                'maxSize': MAX_AUDIO_SIZE_BYTES
            })
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        logger.error(f'❌ Transcription error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/tools/status')
def tools_status():
    """Check status of all AI tools."""
    ollama_ok = check_ollama_connection()
    return jsonify({
        'ollama_connected': ollama_ok,
        'model': MODEL_NAME,
        'tools': {
            'chatWithDocuments': {'available': ollama_ok},
            'transcriptCleaner': {'available': ollama_ok},
            'audioTranscription': {
                'available': WHISPER_AVAILABLE,
                'maxFileSizeMB': MAX_AUDIO_SIZE_MB
            }
        },
        'activeDocumentSessions': len(document_store)
    })


@app.route('/stats')

def stats():
    """
    Get detailed statistics in JSON format
    Useful for monitoring dashboards and debugging
    """
    return jsonify({
        'provider_id': PROVIDER_ID,
        'model': MODEL_NAME,
        'gpu_type': GPU_TYPE,
        'metrics': metrics.get_stats(),
        'system': get_system_info(),
        'config': {
            'ollama_host': OLLAMA_HOST,
            'max_queue_size': MAX_QUEUE_SIZE,
        },
        'timestamp': datetime.utcnow().isoformat(),
    })

@app.before_request
def log_request():
    """Log all incoming requests for debugging"""
    logger.debug(f"{request.method} {request.path} from {request.remote_addr}")

# ============================================================================
# 7-DAY CHAT AUTO-DELETE CLEANUP JOB
# ============================================================================

def cleanup_inactive_chats():
    """Delete chats that haven't been updated in 7 days (except archived)"""
    try:
        logger.info('Running 7-day cleanup job...')
        chats_root = Path(CHATS_DIR)
        current_time = time.time()
        seven_days_seconds = 7 * 24 * 60 * 60
        deleted_count = 0
        
        # Iterate through all users
        for principal_dir in chats_root.iterdir():
            if not principal_dir.is_dir():
                continue
            
            principal_id = principal_dir.name
            metadata_path = principal_dir / 'metadata.json'
            
            if not metadata_path.exists():
                continue
            
            try:
                # Load metadata
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                chats_to_keep = []
                
                # Check each chat
                for chat in metadata.get('chats', []):
                    last_updated = chat.get('lastUpdated', 0) / 1000  # Convert ms to seconds
                    is_archived = chat.get('isArchived', False)
                    
                    # Skip archived chats
                    if is_archived:
                        chats_to_keep.append(chat)
                        continue
                    
                    # Check if older than 7 days
                    if current_time - last_updated > seven_days_seconds:
                        # Delete the chat file
                        chat_file = principal_dir / f"{chat['chatId']}.json"
                        if chat_file.exists():
                            chat_file.unlink()
                            deleted_count += 1
                            logger.info(f'Deleted inactive chat: {chat["chatId"]}')
                    else:
                        chats_to_keep.append(chat)
                
                # Update metadata
                metadata['chats'] = chats_to_keep
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
            
            except Exception as e:
                logger.error(f'Error processing user {principal_id}: {e}')
                continue
        
        logger.info(f'Cleanup complete: deleted {deleted_count} inactive chats')
    
    except Exception as e:
        logger.error(f'Cleanup job error: {e}', exc_info=True)

# Schedule cleanup job to run daily at 2 AM
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_inactive_chats, 'cron', hour=2, minute=0, id='chat_cleanup')

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Endpoint not found',
        'provider_id': PROVIDER_ID,
        'available_endpoints': [
            '/health', '/generate', '/stats',
            '/chat/autosave', '/chat/list', '/chat/{chatId}',
            '/chat/{chatId}/archive', '/chat/recover-archives', '/chat/archive/{cid}'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {e}", exc_info=True)
    return jsonify({
        'error': 'Internal server error',
        'provider_id': PROVIDER_ID
    }), 500

# ===== STARTUP =====

def warmup_model():
    """
    Warm up the model by making a test request.
    This pre-loads the model into memory so the first user request doesn't have to wait.
    """
    logger.info("🔥 Warming up model - this may take a few minutes on first run...")
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": "Hello, this is a warmup request.",
                "stream": False,
                "options": {
                    "num_predict": 10,  # Only generate a few tokens
                    "temperature": 0.7,
                }
            },
            timeout=300  # 5 minute timeout for model download
        )
        
        if response.status_code == 200:
            logger.info(f"✓ Model warmed up successfully! Ready to serve requests.")
            return True
        else:
            logger.warning(f"⚠ Warmup request failed with status {response.status_code}")
            return False
            
    except requests.Timeout:
        logger.error("❌ Model warmup timed out - model may still be downloading")
        logger.error("   First user request may be slow while model finishes loading")
        return False
    except Exception as e:
        logger.error(f"❌ Model warmup failed: {e}")
        return False


if __name__ == '__main__':
    logger.info("=" * 70)
    logger.info("🚀 Trinity Inference Server - Unified Backend")
    logger.info("=" * 70)
    logger.info(f"Backend: {MODEL_BACKEND}")
    logger.info(f"Model: {MODEL_NAME}")
    logger.info(f"Provider ID: {PROVIDER_ID}")
    logger.info(f"GPU Type: {GPU_TYPE}")
    logger.info(f"Max Queue Size: {MAX_QUEUE_SIZE}")
    logger.info(f"Chats Directory: {CHATS_DIR}")
    logger.info(f"Ollama Host: {OLLAMA_HOST}")
    logger.info("=" * 70)
    
    # Check Ollama connection
    if check_ollama_connection():
        logger.info(f"✅ Successfully connected to Ollama ({MODEL_NAME})")
        warmup_model()
    else:
        logger.warning("⚠️  Could not connect to Ollama - server will start anyway")
        logger.warning("   Make sure Ollama is running: ollama serve")
        logger.warning(f"   Make sure model is available: ollama pull {MODEL_NAME}")
    
    # Start background scheduler for cleanup jobs
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Cleanup scheduler started (runs daily at 2 AM)")
    
    # Run Flask app
    logger.info(f"🌐 Starting Flask server on port 8000")
    logger.info("=" * 70)
    
    app.run(
        host='0.0.0.0',
        port=8000,
        threaded=True,
        debug=False
    )

