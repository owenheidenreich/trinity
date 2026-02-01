"""
Trinity Backend - Configuration Module
All environment variables and constants in one place
"""

import os
import logging
from pathlib import Path
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce werkzeug HTTP request log spam
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# ===== HTTP SESSION WITH CONNECTION POOLING =====
# Reuse connections for better performance
def create_http_session():
    """Create a requests session with connection pooling and retries."""
    session = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
    )
    
    # Configure adapters with connection pooling
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,  # Number of connection pools
        pool_maxsize=20,      # Connections per pool
    )
    
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session

# Global HTTP session for reuse
http_session = create_http_session()

# ===== SERVER CONFIGURATION =====
PROVIDER_ID = os.getenv('PROVIDER_ID', 'local-mac-mini')
MODEL_NAME = os.getenv('MODEL_NAME', 'phi3')
MODEL_BACKEND = os.getenv('MODEL_BACKEND', 'ollama')
GPU_TYPE = os.getenv('GPU_TYPE', 'CPU')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '10'))
CHATS_DIR = os.getenv('CHATS_DIR', '/var/lib/trinity/chats')

# ===== LIGHTHOUSE / FILECOIN CONFIGURATION =====
LIGHTHOUSE_API_KEY = os.getenv('LIGHTHOUSE_API_KEY', '')
LIGHTHOUSE_NODE = 'https://upload.lighthouse.storage'
LIGHTHOUSE_API = 'https://api.lighthouse.storage'
LIGHTHOUSE_GATEWAY = 'https://gateway.lighthouse.storage'

# Legacy fallback for old env var name
if not LIGHTHOUSE_API_KEY:
    LIGHTHOUSE_API_KEY = os.getenv('FILECOIN_API_KEY', '')

# ===== AKASH CONFIGURATION =====
AKASH_WALLET_ADDRESS = os.getenv('AKASH_WALLET_ADDRESS', 'akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp')
ICP_BACKEND_CANISTER = os.getenv('ICP_BACKEND_CANISTER', 'au5zq-2qaaa-aaaal-qtowa-cai')
ICP_FRONTEND_CANISTER = os.getenv('ICP_FRONTEND_CANISTER', 'zc67k-kiaaa-aaaal-qtmiq-cai')

# Deployment tier detection
tier_names = {
    'tinyllama:1.1b': 1,
    'llama3.1:8b': 2,
    'qwen2.5:72b': 3,
}
DEPLOYMENT_TIER = tier_names.get(MODEL_NAME, 0)

# ===== BUILD INFO =====
BUILD_TIMESTAMP = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')

# ===== WEB SEARCH CONFIGURATION =====
# Brave Search API - sign up at https://brave.com/search/api/
BRAVE_SEARCH_API_KEY = os.getenv('BRAVE_SEARCH_API_KEY', '')

# ===== AUTHENTICATION =====
AUTH_TIMESTAMP_WINDOW_MS = 5 * 60 * 1000  # 5 minutes

# ===== PROMPT VALIDATION =====
MAX_PROMPT_LENGTH = 50000  # 50KB max prompt to prevent DoS

# ===== ENCRYPTION =====
PBKDF2_ITERATIONS = 100000
ENCRYPTION_KEY_LENGTH = 32  # 256 bits

# ===== PATHS =====
# Only create directories in production (not during import for tests)
try:
    Path(CHATS_DIR).mkdir(parents=True, exist_ok=True)
except PermissionError:
    # Running locally without Docker - use temp directory
    CHATS_DIR = '/tmp/trinity/chats'
    Path(CHATS_DIR).mkdir(parents=True, exist_ok=True)
    logger.warning(f'⚠️ Using temp directory for chats: {CHATS_DIR}')

# Log startup configuration
logger.info(f'🏗️  Trinity Backend Build: {BUILD_TIMESTAMP}')
logger.info(f'📦 Model: {MODEL_NAME} (Tier {DEPLOYMENT_TIER})')
logger.info(f'🔗 Ollama: {OLLAMA_HOST}')
logger.info(f'💾 Chats: {CHATS_DIR}')
