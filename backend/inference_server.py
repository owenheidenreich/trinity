"""
Trinity Inference Server
Production backend using Ollama for model inference
"""

from flask import Flask, request, jsonify
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

# Encryption imports
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2

# ICP Authentication
from icp_auth import require_auth, verify_request_auth

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ===== CONFIGURATION =====
# These can be overridden by environment variables for Akash deployment
PROVIDER_ID = os.getenv('PROVIDER_ID', 'local-mac-mini')
MODEL_NAME = os.getenv('MODEL_NAME', 'phi3')
MODEL_BACKEND = os.getenv('MODEL_BACKEND', 'ollama')  # Always use Ollama
GPU_TYPE = os.getenv('GPU_TYPE', 'CPU')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '10'))
CHATS_DIR = os.getenv('CHATS_DIR', '/var/lib/trinity/chats')

# ===== LIGHTHOUSE / FILECOIN CONFIGURATION =====
# Lighthouse replaces Pinata for decentralized IPFS + Filecoin storage
# Get API key from: https://files.lighthouse.storage
LIGHTHOUSE_API_KEY = os.getenv('LIGHTHOUSE_API_KEY', '')

# Lighthouse API endpoints (from official SDK lighthouse.config.js)
LIGHTHOUSE_NODE = 'https://upload.lighthouse.storage'    # For uploads
LIGHTHOUSE_API = 'https://api.lighthouse.storage'        # For metadata/status
LIGHTHOUSE_GATEWAY = 'https://gateway.lighthouse.storage'  # For downloads

# Legacy fallback - support old env var name during transition
if not LIGHTHOUSE_API_KEY:
    LIGHTHOUSE_API_KEY = os.getenv('FILECOIN_API_KEY', '')

# Build timestamp for pipeline verification
BUILD_TIMESTAMP = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
logger.info(f'🏗️  Trinity Backend Build: {BUILD_TIMESTAMP}')

# Create directories
Path(CHATS_DIR).mkdir(parents=True, exist_ok=True)

# ===== GLOBAL STATE =====

# ===== ENCRYPTION UTILITIES =====
class EncryptionUtils:
    """Handle AES-256-GCM encryption for chat content"""
    
    @staticmethod
    def derive_key(principal_id: str, salt: bytes) -> bytes:
        """Derive encryption key from principal ID using PBKDF2"""
        from Crypto.Hash import SHA256
        return PBKDF2(principal_id, salt, dkLen=32, count=100000, hmac_hash_module=SHA256)
    
    @staticmethod
    def encrypt_chat(chat_data: Dict, principal_id: str) -> Dict:
        """Encrypt chat content"""
        salt = get_random_bytes(16)
        key = EncryptionUtils.derive_key(principal_id, salt)
        
        # Serialize chat data
        plaintext = json.dumps(chat_data).encode('utf-8')
        
        # Generate nonce and encrypt
        cipher = AES.new(key, AES.MODE_GCM)
        nonce = cipher.nonce
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        
        return {
            'version': '1.0',
            'encryption': {
                'algorithm': 'AES-256-GCM',
                'salt': base64.b64encode(salt).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'tag': base64.b64encode(tag).decode('utf-8')
            },
            'encryptedContent': base64.b64encode(ciphertext).decode('utf-8'),
            'fileMetadata': {
                'principalId': principal_id,
                'createdAt': chat_data.get('metadata', {}).get('createdAt', int(time.time() * 1000)),
                'contentType': 'application/json'
            }
        }
    
    @staticmethod
    def decrypt_chat(encrypted_data: Dict, principal_id: str) -> Dict:
        """Decrypt chat content"""
        try:
            salt = base64.b64decode(encrypted_data['encryption']['salt'])
            nonce = base64.b64decode(encrypted_data['encryption']['nonce'])
            tag = base64.b64decode(encrypted_data['encryption']['tag'])
            ciphertext = base64.b64decode(encrypted_data['encryptedContent'])
            
            key = EncryptionUtils.derive_key(principal_id, salt)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
            return json.loads(plaintext.decode('utf-8'))
        except Exception as e:
            logger.error(f'Decryption failed: {e}')
            raise ValueError('Failed to decrypt chat - wrong principal or corrupted data')

# ===== ICP SIGNATURE VERIFICATION =====
def verify_icp_signature(principal_id: str, timestamp: str, signature: str) -> Tuple[bool, Optional[str]]:
    """Verify ICP Internet Identity signature"""
    try:
        # Check timestamp is recent (within 5 minutes)
        request_time = int(timestamp)
        current_time = int(time.time() * 1000)
        time_diff = abs(current_time - request_time)
        
        if time_diff > 5 * 60 * 1000:  # 5 minutes
            return False, 'Timestamp too old'
        
        # NOTE: Full ICP signature verification would require @dfinity/agent library
        # For now, just verify timestamp freshness and principal format
        if not principal_id or len(principal_id) < 10:
            return False, 'Invalid principal format'
        
        logger.debug(f'Signature verification passed for {principal_id}')
        return True, None
    except Exception as e:
        logger.error(f'Signature verification error: {e}')
        return False, str(e)

def require_auth(f):
    """Decorator to require ICP authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        principal = request.headers.get('ICP-Principal')
        signature = request.headers.get('ICP-Signature')
        timestamp = request.headers.get('ICP-Timestamp')
        
        if not all([principal, signature, timestamp]):
            logger.warning('Missing authentication headers')
            return jsonify({'error': 'Missing authentication headers'}), 401
        
        valid, error = verify_icp_signature(principal, timestamp, signature)
        if not valid:
            logger.warning(f'Invalid signature for principal {principal}: {error}')
            return jsonify({'error': error or 'Invalid signature'}), 401
        
        # Set principal on request object for use in route handler
        request.principal = principal
        logger.debug(f'✅ Authenticated request from {principal}')
        
        return f(*args, **kwargs)
    
    return decorated_function

# ===== FILE STORAGE MANAGEMENT =====
def get_user_dir(principal_id: str) -> Path:
    """Get user's chat directory"""
    user_dir = Path(CHATS_DIR) / principal_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir

def get_metadata_path(principal_id: str) -> Path:
    """Get metadata file path for user"""
    return get_user_dir(principal_id) / 'metadata.json'

def get_user_memory_path(principal_id: str) -> Path:
    """Get user memory file path"""
    return get_user_dir(principal_id) / 'user_memory.json'

def load_user_memory(principal_id: str) -> Dict:
    """Load user's persistent memory"""
    path = get_user_memory_path(principal_id)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {
        'principalId': principal_id,
        'version': '1.0',
        'facts': [],  # List of important facts about the user
        'preferences': {},  # User preferences
        'createdAt': int(time.time() * 1000),
        'lastUpdated': int(time.time() * 1000)
    }

def save_user_memory(principal_id: str, memory: Dict):
    """Save user's persistent memory"""
    memory['lastUpdated'] = int(time.time() * 1000)
    with open(get_user_memory_path(principal_id), 'w') as f:
        json.dump(memory, f, indent=2)

def load_metadata(principal_id: str) -> Dict:
    """Load user's metadata"""
    path = get_metadata_path(principal_id)
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {
        'principalId': principal_id,
        'version': '1.0',
        'chats': [],
        'createdAt': int(time.time() * 1000),
        'lastLogin': int(time.time() * 1000),
        # Bundle tracking fields for Pinata sync
        'currentBundleCID': None,
        'lastBundleVersion': 0,
        'lastSyncedAt': None
    }

def save_metadata(principal_id: str, metadata: Dict):
    """Save user's metadata"""
    metadata['lastLogin'] = int(time.time() * 1000)
    with open(get_metadata_path(principal_id), 'w') as f:
        json.dump(metadata, f, indent=2)

# ============================================================================
# LIGHTHOUSE / FILECOIN INTEGRATION
# ============================================================================
# Lighthouse provides IPFS pinning + verified Filecoin storage deals.
# Unlike Pinata, Lighthouse creates actual Filecoin deals for long-term storage.
#
# API Flow:
#   1. Upload: POST to /api/v0/add -> returns CID immediately
#   2. Filecoin deal: Created automatically (takes 1-24 hours to seal)
#   3. Retrieval: Any IPFS gateway using the CID
#
# Documentation: https://docs.lighthouse.storage
# ============================================================================

def upload_to_filecoin(file_data: bytes, filename: str, principal_id: str = None, is_master_bundle: bool = False) -> Optional[str]:
    """
    Upload file to IPFS + Filecoin via Lighthouse.
    
    Lighthouse automatically queues uploaded content for Filecoin verified deals.
    The CID is available immediately via IPFS; Filecoin deal seals in 1-24 hours.

    Args:
        file_data: The encrypted data to upload
        filename: Name for the file (used for tracking)
        principal_id: User's principal ID (stored in local metadata only)
        is_master_bundle: If True, marks this as the user's master bundle

    Returns:
        CID string on success, None on failure
    """
    if not LIGHTHOUSE_API_KEY:
        logger.warning('Lighthouse API key not configured - skipping archive')
        return None

    try:
        # Lighthouse uses /api/v0/add endpoint for uploads
        endpoint = f'{LIGHTHOUSE_NODE}/api/v0/add'
        
        headers = {
            'Authorization': f'Bearer {LIGHTHOUSE_API_KEY}'
        }
        
        # Create form data with the file
        # Lighthouse accepts multipart/form-data with 'file' field
        files = {
            'file': (filename, file_data, 'application/json')
        }
        
        logger.info(f'📤 Uploading to Lighthouse: {filename} ({len(file_data)} bytes)')
        
        response = requests.post(
            endpoint,
            headers=headers,
            files=files,
            timeout=60  # 60 second timeout for upload
        )

        if response.status_code == 200:
            result = response.json()
            cid = result.get('Hash')
            size = result.get('Size', len(file_data))
            
            logger.info(f'✅ Uploaded to Lighthouse/IPFS: {cid}')
            logger.info(f'   Size: {size} bytes')
            logger.info(f'   Principal: {principal_id}')
            logger.info(f'   Gateway: {LIGHTHOUSE_GATEWAY}/ipfs/{cid}')
            logger.info(f'   ⏳ Filecoin deal will be created automatically (1-24 hours)')
            
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
    
    Note: Lighthouse associates files with the API key, not with custom metadata.
    To support multi-user, we store principal -> CID mapping in local metadata.
    This function returns all uploads for the current API key.

    Args:
        principal_id: User's principal ID (for logging, filtering done locally)
        file_type: Optional filter - not used in Lighthouse API, filter locally

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

        # Lighthouse uses /api/user/files_uploaded endpoint
        response = requests.get(
            f'{LIGHTHOUSE_API}/api/user/files_uploaded',
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            files = result.get('fileList', [])
            
            # Sort by createdAt descending (newest first)
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
    This function returns the current deal status.

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
        # Try multiple IPFS gateways - Lighthouse first since we upload there
        gateways = [
            f'{LIGHTHOUSE_GATEWAY}/ipfs/{cid}',  # Lighthouse gateway (primary)
            f'https://ipfs.io/ipfs/{cid}',        # Protocol Labs gateway
            f'https://dweb.link/ipfs/{cid}',      # dweb.link gateway
            f'https://cloudflare-ipfs.com/ipfs/{cid}'  # Cloudflare gateway
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
            logger.info(f'💾 ICP cached response for request_id: {request_id}')
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


# ===== HELPER FUNCTIONS =====
def build_prompt_with_context(user_prompt: str, context_messages: list, user_memory: Dict = None) -> str:
    """
    Build a prompt that includes conversation context and user memory for the LLM.
    Supports system messages for conversation summaries and persistent user facts.
    
    Args:
        user_prompt: The current user message
        context_messages: Array of recent messages [{ role: 'user'|'assistant'|'system', content: '...' }]
        user_memory: Optional dict with user's persistent memory (facts, preferences)
    
    Returns:
        Full prompt string with context
    """
    conversation_parts = []
    
    # 1. Add user memory facts if available (persistent across all chats)
    if user_memory and user_memory.get('facts'):
        facts = user_memory['facts']
        if len(facts) > 0:
            facts_text = "\n".join([f"- {fact['fact']}" for fact in facts[-10:]])  # Last 10 facts
            conversation_parts.append(f"[User Background - Remember these facts]\n{facts_text}\n")
    
    # 2. Add conversation context
    if not context_messages or len(context_messages) == 0:
        # No context messages, just user memory (if any) + prompt
        if len(conversation_parts) > 0:
            conversation_parts.append(f"\nUser: {user_prompt}")
            conversation_parts.append("\nAssistant:")
            return "\n".join(conversation_parts)
        else:
            return user_prompt
    
    # 3. Build conversation history from context messages
    for msg in context_messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'system':
            # System message (conversation summary) - insert after user memory
            conversation_parts.insert(len(conversation_parts), f"[Context Summary]\n{content}\n")
        elif role == 'user':
            conversation_parts.append(f"User: {content}")
        elif role == 'assistant':
            conversation_parts.append(f"Assistant: {content}")
    
    conversation_parts.append(f"\nCurrent user message: {user_prompt}")
    conversation_parts.append("\nAssistant:")
    
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
        max_length = data.get('max_length', 150)
        context_memory = data.get('contextMemory', [])
        principal = data.get('principal')  # Optional for unauthenticated requests
        
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
        
        # Build prompt with context and user memory
        full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)
        
        # Privacy: Log word count and hash only - don't expose prompt content
        import hashlib
        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:8]
        word_count = len(user_prompt.split())
        logger.info(f"[{PROVIDER_ID}] Processing: {word_count} words (hash:{prompt_hash}) with {len(context_memory)} context messages")
        if len(context_memory) > 0:
            logger.info(f"[{PROVIDER_ID}] Context: {len(context_memory)} messages totaling {sum(len(m.get('content', '').split()) for m in context_memory)} words")
        
        logger.info(f"[{PROVIDER_ID}] Full prompt length: {len(full_prompt)} chars")
        
        # Generate with Ollama
        logger.info(f"🤖 Generating with Ollama (seed={seed}, temp={temperature})")
        
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
            timeout=120
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
# NEW ENDPOINTS: CHAT PERSISTENCE & ARCHIVE
# ============================================================================

@app.route('/chat/autosave', methods=['POST'])
@require_auth
def autosave_chat():
    """Save chat after each message exchange"""
    try:
        # Principal is set by @require_auth decorator
        principal = request.principal
        data = request.json
        
        logger.info(f'📥 Autosave request from {principal}')
        logger.info(f'   Request data keys: {data.keys() if data else "None"}')
        
        chat_id = data.get('chatId')
        messages = data.get('messages', [])
        metadata = data.get('metadata', {})
        
        logger.info(f'   chatId: {chat_id}')
        logger.info(f'   messages: {len(messages)} messages')
        logger.info(f'   metadata: {metadata}')
        
        if not chat_id:
            logger.error('❌ Missing chatId in autosave request')
            return jsonify({'error': 'Missing chatId'}), 400
        
        # Prepare chat data for encryption
        chat_data = {
            'chatId': chat_id,
            'messages': messages,
            'metadata': metadata
        }
        
        logger.info(f'🔐 Encrypting chat data...')
        # Encrypt content
        encrypted = EncryptionUtils.encrypt_chat(chat_data, principal)
        logger.info(f'✅ Encryption complete')
        
        # Save to disk
        chat_filename = f"{chat_id}.json"
        chat_path = get_user_dir(principal) / chat_filename
        
        logger.info(f'💾 Saving to: {chat_path}')
        with open(chat_path, 'w') as f:
            json.dump(encrypted, f)
        logger.info(f'✅ File saved')
        
        # Update metadata
        logger.info(f'📋 Updating metadata...')
        user_metadata = load_metadata(principal)
        
        # Find or create chat entry in metadata
        chat_entry = next((c for c in user_metadata['chats'] if c['chatId'] == chat_id), None)
        if not chat_entry:
            logger.info(f'📝 Creating new chat entry in metadata')
            chat_entry = {
                'chatId': chat_id,
                'title': metadata.get('title', 'Untitled'),
                'createdAt': int(time.time() * 1000),
                'isArchived': False
            }
            user_metadata['chats'].append(chat_entry)
        else:
            logger.info(f'📝 Updating existing chat entry in metadata')
        
        chat_entry['lastUpdated'] = metadata.get('updatedAt', int(time.time() * 1000))
        chat_entry['messageCount'] = len(messages)
        
        save_metadata(principal, user_metadata)
        logger.info(f'✅ Metadata saved')
        
        logger.info(f'✅ Chat autosaved successfully: {chat_id} for {principal}')
        
        return jsonify({
            'success': True,
            'chatId': chat_id,
            'savedAt': int(time.time() * 1000),
            'nextAutoDeleteAt': int(time.time() * 1000) + (7 * 24 * 60 * 60 * 1000)
        })
    
    except Exception as e:
        logger.error(f'❌ Autosave error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat/list', methods=['GET'])
@require_auth
def list_chats():
    """List all chats for user (includes both active and archived)"""
    try:
        principal = request.principal
        user_metadata = load_metadata(principal)
        
        # Return ALL chats (both active and archived) sorted by last updated
        # Frontend will filter them into separate sections
        chats = user_metadata.get('chats', [])
        chats.sort(key=lambda x: x.get('lastUpdated', 0), reverse=True)
        
        return jsonify({
            'chats': chats,
            'count': len(chats)
        })
    
    except Exception as e:
        logger.error(f'List chats error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<chat_id>', methods=['GET'])
@require_auth
def get_chat(chat_id):
    """Load specific chat"""
    try:
        principal = request.principal
        chat_path = get_user_dir(principal) / f"{chat_id}.json"
        
        if not chat_path.exists():
            return jsonify({'error': 'Chat not found'}), 404
        
        with open(chat_path, 'r') as f:
            encrypted_data = json.load(f)
        
        # Decrypt
        decrypted = EncryptionUtils.decrypt_chat(encrypted_data, principal)
        
        return jsonify(decrypted)
    
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
        
        logger.info(f'📖 Loaded user memory for {principal}: {len(memory.get("facts", []))} facts')
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
        
        logger.info(f'💾 Updated user memory for {principal}')
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
        
        logger.info(f'➕ Added fact to user memory: {new_fact["fact"][:50]}...')
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
        
        logger.info(f'🗑️ Deleted fact from user memory: {deleted_fact["fact"][:50]}...')
        return jsonify({
            'success': True,
            'deletedFact': deleted_fact,
            'totalFacts': len(memory['facts'])
        })
    
    except Exception as e:
        logger.error(f'❌ Error deleting memory fact: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500

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

