"""
Trinity Backend - Configuration Module
All environment variables and constants in one place
"""

import logging
import os
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Reduce werkzeug HTTP request log spam
logging.getLogger("werkzeug").setLevel(logging.WARNING)


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
        pool_maxsize=20,  # Connections per pool
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# Global HTTP session for reuse
http_session = create_http_session()

# ===== SERVER CONFIGURATION =====
PROVIDER_ID = os.getenv("PROVIDER_ID", "local-mac-mini")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3:32b")
# Model routing: use a conversational model for general chat, coder model for code tasks.
MODEL_ROUTING_ENABLED = os.getenv("MODEL_ROUTING_ENABLED", "true").lower() == "true"
CONVERSATION_MODEL_NAME = os.getenv("CONVERSATION_MODEL_NAME", MODEL_NAME)
CODER_MODEL_NAME = os.getenv("CODER_MODEL_NAME", MODEL_NAME)
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ollama")
GPU_TYPE = os.getenv("GPU_TYPE", "CPU")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# Split model capacity between chat (user-facing) and ingestion (background).
OLLAMA_CHAT_HOST = os.getenv("OLLAMA_CHAT_HOST", OLLAMA_HOST)
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", CONVERSATION_MODEL_NAME or MODEL_NAME)
OLLAMA_INGEST_HOST = os.getenv("OLLAMA_INGEST_HOST", OLLAMA_HOST)
# Default ingest model to chat model unless explicitly overridden.
# This prevents background extraction from failing on deployments that only
# pull/configure MODEL_NAME (for example, qwen3:8b test environments).
OLLAMA_INGEST_MODEL = os.getenv("OLLAMA_INGEST_MODEL", OLLAMA_CHAT_MODEL or MODEL_NAME)
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "10"))
CHATS_DIR = os.getenv("CHATS_DIR", "/var/lib/trinity/chats")
# Canonical architecture paths
CANONICAL_FRONTEND_PATH = "src-react"
CANONICAL_GENERATE_ROUTE = "/generate/agent"

# ===== LIGHTHOUSE / FILECOIN CONFIGURATION =====
LIGHTHOUSE_API_KEY = os.getenv("LIGHTHOUSE_API_KEY", "")
LIGHTHOUSE_NODE = "https://upload.lighthouse.storage"
LIGHTHOUSE_API = "https://api.lighthouse.storage"
LIGHTHOUSE_GATEWAY = "https://gateway.lighthouse.storage"

# Legacy fallback for old env var name
if not LIGHTHOUSE_API_KEY:
    LIGHTHOUSE_API_KEY = os.getenv("FILECOIN_API_KEY", "")

# ===== AKASH CONFIGURATION =====
AKASH_WALLET_ADDRESS = os.getenv(
    "AKASH_WALLET_ADDRESS", "akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp"
)
ICP_BACKEND_CANISTER = os.getenv("ICP_BACKEND_CANISTER", "au5zq-2qaaa-aaaal-qtowa-cai")
ICP_FRONTEND_CANISTER = os.getenv("ICP_FRONTEND_CANISTER", "zc67k-kiaaa-aaaal-qtmiq-cai")

# ===== BUILD INFO =====
BUILD_TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

# ===== WEB SEARCH CONFIGURATION =====
# Brave Search API - sign up at https://brave.com/search/api/
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

# ===== AUTHENTICATION =====
# Signed request freshness window (default: 60 seconds)
AUTH_TIMESTAMP_WINDOW_MS = int(os.getenv("AUTH_TIMESTAMP_WINDOW_MS", "60000"))

# Admin principals (comma-separated list of principal IDs that can access /admin/* endpoints)
# Set via environment variable: ADMIN_PRINCIPALS="principal1,principal2"
ADMIN_PRINCIPALS = [p.strip() for p in os.getenv("ADMIN_PRINCIPALS", "").split(",") if p.strip()]

# ===== PROMPT VALIDATION =====
MAX_PROMPT_LENGTH = 100000  # 100KB max prompt (doubled for 64K context window)

# ===== INFERENCE DEFAULTS =====
NUM_CTX = 65536                        # Explicit Ollama context window (prompt + response)
DEFAULT_MAX_TOKENS = 8000             # Default max_length for /generate
REASONING_MIN_TOKENS = 8000        # Min tokens when reasoning mode active
DEFAULT_TEMPERATURE = 0.7          # Default sampling temperature
OLLAMA_TIMEOUT = 600               # Full generation timeout (seconds)
OLLAMA_TIMEOUT_TOOLS = 300         # Tools/summarize timeout (seconds)

# ===== DOCUMENT / CONTEXT LIMITS =====
MAX_DOCUMENT_CONTEXT_CHARS = 60000    # Chars of document context sent to LLM
MAX_WEB_SCRAPE_CHARS = 30000          # Default max chars from browse endpoint
MAX_WEB_SCRAPE_CHARS_CAP = 50000      # Hard cap for browse endpoint
WEB_FETCH_TIMEOUT = 15                # Seconds for URL fetching
WEB_SEARCH_TIMEOUT = 10               # Seconds for search API calls
WEB_SEARCH_MAX_RESULTS = 10           # Hard cap on search results
SEARCH_SUMMARIZE_MAX_SOURCES = 5      # Max sources for search-and-summarize
SEARCH_SUMMARIZE_CHARS_PER_SOURCE = 3000 # Chars extracted per source

# ===== CHAT / STORAGE LIMITS =====
MAX_ARCHIVED_CHATS = 20              # Maximum archived chats per user
IPFS_SCAN_LIMIT = 50                 # Max uploads to scan when listing chats
CHAT_INACTIVE_DAYS = 7               # Days before auto-delete
PRINCIPAL_DISPLAY_LENGTH = 16         # Chars of principal shown in logs/filenames
# Debounce window before autosaved chats checkpoint to IPFS
CHAT_CHECKPOINT_DEBOUNCE_SECONDS = int(os.getenv("CHAT_CHECKPOINT_DEBOUNCE_SECONDS", "45"))
# Hard cap for how long autosave writes can stay unsynced during active chats
CHAT_CHECKPOINT_MAX_WAIT_SECONDS = int(os.getenv("CHAT_CHECKPOINT_MAX_WAIT_SECONDS", "180"))

# ===== SESSION LIMITS =====
MIN_SESSION_HOURS = 1
MAX_SESSION_HOURS = 24

# ===== ENCRYPTION =====
PBKDF2_ITERATIONS = 100000
ENCRYPTION_KEY_LENGTH = 32  # 256 bits

# ===== RAG CONFIGURATION =====
# FastEmbed model for embeddings (33MB, 384 dimensions)
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
# Chunk size for document splitting (tokens)
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
# Number of chunks to retrieve
RAG_TOP_K = 5

# ===== MEMORY CONFIGURATION =====
# Working memory: most recent messages always included
WORKING_MEMORY_SIZE = int(os.getenv("WORKING_MEMORY_SIZE", "5"))
# Semantic memory: retrieved based on relevance
SEMANTIC_MEMORY_SIZE = int(os.getenv("SEMANTIC_MEMORY_SIZE", "8"))
# Recency weight for retrieval scoring (0-1)
RECENCY_WEIGHT = 0.3
# User profile token budget — max tokens for profile section in prompt
PROFILE_TOKEN_BUDGET = int(os.getenv("PROFILE_TOKEN_BUDGET", "3500"))
# Minimum score needed for non-preference facts on non-personal queries
PROFILE_RELEVANCE_FLOOR = float(os.getenv("PROFILE_RELEVANCE_FLOOR", "0.52"))
# Hard cap for total facts packed into prompt memory section
PROFILE_MAX_FACTS = int(os.getenv("PROFILE_MAX_FACTS", "25"))
# Profile categories for structured user data
PROFILE_CATEGORIES = ["identity", "work", "interests", "preferences", "relationships"]
# Dedup merge threshold — update existing fact instead of skipping
DEDUP_MERGE_THRESHOLD = 0.85
# Dedup skip threshold — too similar to save at all
DEDUP_SKIP_THRESHOLD = 0.95
# Whether assistant-generated text is eligible for auto profile extraction
AUTO_EXTRACT_ASSISTANT_MEMORY = os.getenv("AUTO_EXTRACT_ASSISTANT_MEMORY", "false").lower() == "true"
# Async ingestion worker for memory/profile/graph updates
MEMORY_INGESTION_ENABLED = os.getenv("MEMORY_INGESTION_ENABLED", "true").lower() == "true"
MEMORY_INGESTION_QUEUE_MAXSIZE = int(os.getenv("MEMORY_INGESTION_QUEUE_MAXSIZE", "2000"))
# Enforce strict model-capacity isolation: extraction/summarization may only use ingest endpoint.
MEMORY_INGEST_STRICT_ISOLATION = os.getenv("MEMORY_INGEST_STRICT_ISOLATION", "true").lower() == "true"
# Graph memory (Kuzu-backed where available)
GRAPH_MEMORY_ENABLED = os.getenv("GRAPH_MEMORY_ENABLED", "true").lower() == "true"
GRAPH_MEMORY_TOP_K = int(os.getenv("GRAPH_MEMORY_TOP_K", "6"))

# ===== TOOL CONFIGURATION =====
# Enable code execution (RestrictedPython sandbox)
# SECURITY: Disabled by default in production due to sandbox escape risks
# Set CODE_EXECUTION_ENABLED=true only for development/testing
CODE_EXECUTION_ENABLED = os.getenv("CODE_EXECUTION_ENABLED", "false").lower() == "true"
CODE_EXECUTION_TIMEOUT = 5  # seconds
CODE_EXECUTION_MEMORY_LIMIT = 10 * 1024 * 1024  # 10MB

# ===== REACT AGENTIC LOOP =====
# Enable iterative tool calling (think -> act -> observe -> repeat)
REACT_ENABLED = os.getenv("REACT_ENABLED", "true").lower() == "true"
# Maximum tool-calling iterations before forcing a final answer
REACT_MAX_ITERATIONS = int(os.getenv("REACT_MAX_ITERATIONS", "15"))
# Token budget guard — force final answer if approaching context limit
# 75% of context window (64K default → 48K budget)
REACT_TOKEN_BUDGET = int(os.getenv("REACT_TOKEN_BUDGET", "48000"))
# Maximum Reflexion retries for code execution errors
REFLEXION_MAX_RETRIES = int(os.getenv("REFLEXION_MAX_RETRIES", "3"))

# ===== FILESYSTEM TOOLS =====
# Sandbox root for filesystem tools (Docker: /workspace, local: /tmp/trinity/workspace)
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/workspace")
# Max file size for write_file (5MB)
WORKSPACE_MAX_FILE_SIZE = int(os.getenv("WORKSPACE_MAX_FILE_SIZE", str(5 * 1024 * 1024)))
# Max directory listing depth
WORKSPACE_MAX_DEPTH = int(os.getenv("WORKSPACE_MAX_DEPTH", "3"))
# Max search results
WORKSPACE_MAX_SEARCH_RESULTS = int(os.getenv("WORKSPACE_MAX_SEARCH_RESULTS", "50"))
# Allowed commands for run_command tool
WORKSPACE_ALLOWED_COMMANDS = ["python", "python3", "pytest", "node"]
# Command execution timeout (seconds)
WORKSPACE_COMMAND_TIMEOUT = int(os.getenv("WORKSPACE_COMMAND_TIMEOUT", "30"))
# ===== MEMORY TOOLS (MemGPT) =====
MEMORY_TOOLS_ENABLED = os.getenv("MEMORY_TOOLS_ENABLED", "true").lower() == "true"

# ===== MCP (Model Context Protocol) =====
# Enable MCP server (exposes Trinity tools to external MCP clients)
MCP_SERVER_ENABLED = os.getenv("MCP_SERVER_ENABLED", "true").lower() == "true"
# ===== PATHS =====
# Only create directories in production (not during import for tests)
try:
    Path(CHATS_DIR).mkdir(parents=True, exist_ok=True)
except PermissionError:
    # Running locally without Docker - use temp directory
    CHATS_DIR = "/tmp/trinity/chats"
    Path(CHATS_DIR).mkdir(parents=True, exist_ok=True)
    logger.warning(f"⚠️ Using temp directory for chats: {CHATS_DIR}")

# Log startup configuration
logger.info(f"🏗️  Trinity Backend Build: {BUILD_TIMESTAMP}")
logger.info(f"📦 Model: {MODEL_NAME}")
logger.info(f"🔗 Ollama: {OLLAMA_HOST}")
logger.info(f"💾 Chats: {CHATS_DIR}")
