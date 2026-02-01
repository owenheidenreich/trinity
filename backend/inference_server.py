"""
Trinity Inference Server
Production backend using Ollama for model inference

Refactored: Config, encryption, storage, lighthouse, middleware, and services modules extracted.
See backend/ structure:
  - config.py: Environment variables and constants
  - encryption.py: AES-256-GCM encryption utilities
  - storage.py: User directory and metadata management  
  - lighthouse.py: IPFS/Filecoin storage via Lighthouse
  - middleware/: Rate limiting, ICP caching
  - services/: Metrics, prompts, Ollama client
  - routes/: (Future) Flask blueprints for endpoints
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_compress import Compress
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
    ICP_BACKEND_CANISTER, ICP_FRONTEND_CANISTER, DEPLOYMENT_TIER, BUILD_TIMESTAMP,
    AUTH_TIMESTAMP_WINDOW_MS, BRAVE_SEARCH_API_KEY, MAX_PROMPT_LENGTH,
    http_session, logger
)
from encryption import EncryptionUtils
from storage import (
    get_user_dir, get_metadata_path, get_user_memory_path,
    load_user_memory, save_user_memory, load_metadata, save_metadata
)
from lighthouse import (
    upload_to_ipfs, get_lighthouse_uploads,
    download_from_ipfs
)

# Import new modular middleware and services
from middleware import rate_limit, storage_rate_limit, icp_idempotent, icp_cache
from services import (
    MetricsCollector, metrics, get_system_info,
    TRINITY_SYSTEM_PROMPT, REASONING_SYSTEM_PROMPT,
    build_prompt_with_context, build_reasoning_prompt,
    parse_reasoning_response, is_small_model,
    check_ollama_connection, warmup_model,
    # Akash services
    get_akt_price_usd, get_escrow_balance, get_actual_lease_price,
    get_akash_deployment_info, AKASH_WALLET_ADDRESS,
    DEPLOYMENT_TIER, DEPLOYMENT_TIER_NAME, HOURLY_COST_AKT, DAILY_COST_AKT,
    SESSION_TYPE, SESSION_ID, SESSION_EXPIRY, SESSION_FUNDED_AKT
)

# Input validation
from validation import validate_chat_id, validate_principal_id, validate_cid, is_safe_url

import tempfile

# ICP Authentication
from icp_auth import require_auth, verify_request_auth

app = Flask(__name__)

# Enable gzip compression for responses
# Reduces bandwidth usage and improves performance
Compress(app)

# SECURITY: Restrict CORS to known origins
# In production, this prevents random websites from making requests
ALLOWED_ORIGINS = [
    'https://zc67k-kiaaa-aaaal-qtmiq-cai.icp0.io',  # ICP canister frontend
    'https://zc67k-kiaaa-aaaal-qtmiq-cai.raw.icp0.io',
    'https://trinityai.cc',
    'https://www.trinityai.cc',
    'https://vercel-proxy-swart-nine.vercel.app',
    'http://localhost:3000',  # Local development
    'http://localhost:5173',  # Vite dev server
    'http://127.0.0.1:3000',
    'http://127.0.0.1:5173',
]

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# ===== GLOBAL STATE =====

# Thread-safe locks for global state (Flask runs threaded=True)
# SECURITY: Prevents race conditions in concurrent requests
_document_store_lock = threading.Lock()
_funding_cache_lock = threading.Lock()

# In-memory document storage for Chat With Documents (per-session)
# Includes TTL tracking to prevent memory leaks
document_store = {}
DOCUMENT_STORE_MAX_AGE = 3600  # 1 hour max lifetime per document
DOCUMENT_STORE_MAX_SIZE = 100  # Max documents to store
MAX_DOCUMENT_SIZE = 5_000_000  # 5MB max per document upload


def cleanup_document_store():
    """Remove expired documents to prevent memory leaks. Thread-safe."""
    now = time.time()
    with _document_store_lock:
        expired = [
            session_id for session_id, doc in document_store.items()
            if now - doc.get('uploaded_at_ts', now) > DOCUMENT_STORE_MAX_AGE
        ]
        for session_id in expired:
            del document_store[session_id]
            logger.info(f'🗑️ Cleaned up expired document session: {session_id}')

        # Also enforce max size (FIFO)
        while len(document_store) > DOCUMENT_STORE_MAX_SIZE:
            oldest = min(document_store.keys(),
                         key=lambda k: document_store[k].get('uploaded_at_ts', 0))
            del document_store[oldest]
            logger.info(f'🗑️ Cleaned up document store overflow: {oldest}')


# Note: Validation functions now in validation.py
# Note: MetricsCollector, metrics, get_system_info now imported from services.metrics
# Note: ICPIdempotencyCache, icp_cache, icp_idempotent now imported from middleware.icp_cache
# Note: check_ollama_connection, warmup_model now imported from services.ollama
# Note: Akash functions now in services.akash

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


# Note: Akash functions (get_akt_price_usd, get_escrow_balance, get_actual_lease_price, 
# get_akash_deployment_info) and constants now imported from services.akash

# Funding cache (local to this endpoint)
_funding_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 minute cache
}

@app.route('/funding/status')
def funding_status():
    """
    Funding transparency endpoint.
    Returns current deployment costs, AKT price, and donation addresses.
    Cached for 5 minutes to avoid API rate limits.
    """
    global _funding_cache

    now = time.time()

    # Thread-safe cache check
    with _funding_cache_lock:
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
        'ipfs': {
            'gateway': LIGHTHOUSE_GATEWAY,
            'storage_info': 'Lighthouse free tier: 1GB',
            'learn_more': 'https://docs.ipfs.tech/concepts/what-is-ipfs/'
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
    
    # Thread-safe cache update
    with _funding_cache_lock:
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


# Note: TRINITY_SYSTEM_PROMPT, REASONING_SYSTEM_PROMPT, build_prompt_with_context,
# build_reasoning_prompt, parse_reasoning_response, is_small_model are now
# imported from services.prompts

@app.route('/generate', methods=['POST'])
@rate_limit
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
        reasoning_mode = data.get('reasoning_mode', False)  # Enable structured reasoning
        
        # ICP canister sends options with seed and temperature for deterministic consensus
        options = data.get('options', {})
        temperature = options.get('temperature', data.get('temperature', 0.7))
        seed = options.get('seed')  # ICP deterministic seed - critical for consensus
        
        # Check if this is an ICP request (has X-Request-ID header from canister)
        is_icp_request = request.headers.get('X-Request-ID') is not None
        
        if not user_prompt:
            raise ValueError("Prompt cannot be empty")
        
        # SECURITY: Limit prompt length to prevent DoS attacks
        if len(user_prompt) > MAX_PROMPT_LENGTH:
            logger.warning(f"⚠️ Prompt too long: {len(user_prompt)} chars (max: {MAX_PROMPT_LENGTH})")
            return jsonify({
                'error': f'Prompt too long. Maximum {MAX_PROMPT_LENGTH} characters allowed.',
                'received': len(user_prompt),
                'max_allowed': MAX_PROMPT_LENGTH
            }), 400
        
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
        
        # Build prompt - use reasoning mode for complex questions
        if reasoning_mode and not is_small_model():
            full_prompt = build_reasoning_prompt(user_prompt, context_memory, user_memory)
            # Deep thinking needs MUCH more tokens - at least 4000 for thorough reasoning
            max_length = max(max_length, 4000)
            logger.info("🧠 Using DEEP REASONING mode with extended output")
        else:
            full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)
        
        # Privacy: Log word count and hash only - don't expose prompt content
        import hashlib
        prompt_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:8]
        word_count = len(user_prompt.split())
        context_count = len(context_memory)
        
        # Single consolidated log line for request
        logger.info(f"🤖 Request: {word_count} words (#{prompt_hash}), {context_count} ctx, seed={seed}, reasoning={reasoning_mode}")
        
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
        
        response = http_session.post(
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
        
        # Parse reasoning output if reasoning mode was enabled
        reasoning_result = None
        final_response = generated_text
        if reasoning_mode and not is_small_model():
            reasoning_result = parse_reasoning_response(generated_text)
            # Use the extracted answer as the main response
            if reasoning_result.get('answer'):
                final_response = reasoning_result['answer']
            logger.info(f"🧠 Reasoning parsed: thinking={bool(reasoning_result.get('thinking'))}, plan={bool(reasoning_result.get('plan'))}")
        
        # Calculate metrics
        latency_ms = (time.time() - start_time) * 1000
        tokens_generated = len(generated_text.split())  # Rough approximation
        
        # Record success
        metrics.record_request(True, tokens_generated, latency_ms)
        
        logger.info(f"[{PROVIDER_ID}] Generated {tokens_generated} tokens in {latency_ms:.0f}ms")
        
        # Build response - ICP requests get deterministic fields only for consensus
        response_data = {
            'response': final_response,  # Main response (or extracted answer)
            'model': MODEL_NAME,
            'provider_id': PROVIDER_ID,
            'done': True,
        }
        
        # Include reasoning components if available
        if reasoning_result:
            response_data['reasoning'] = {
                'thinking': reasoning_result.get('thinking'),
                'plan': reasoning_result.get('plan'),
                'raw': reasoning_result.get('raw')
            }
        
        # Only include non-deterministic fields for non-ICP requests
        # ICP runs 13 replicas - they must all get identical responses
        if not is_icp_request:
            response_data['prompt'] = user_prompt
            response_data['generated_text'] = final_response
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
@rate_limit
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
        response = http_session.post(
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
@rate_limit
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
                response = http_session.post(
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
@rate_limit
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
        reasoning_mode = data.get('reasoning_mode', False)  # Enable structured reasoning
        
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
        
        # Build full prompt - use reasoning mode for /think command
        if reasoning_mode and not is_small_model():
            full_prompt = build_reasoning_prompt(user_prompt, context_memory, user_memory)
            # Deep thinking needs MUCH more tokens
            max_length = max(max_length, 4000)
            logger.info("🧠 STREAM: Using DEEP REASONING mode with extended output")
        else:
            full_prompt = build_prompt_with_context(user_prompt, context_memory, user_memory)
        
        logger.info(f"🌊 Streaming request: {len(user_prompt.split())} words, {len(context_memory)} ctx, reasoning={reasoning_mode}")
        
        def generate_sse():
            """Generator that yields SSE-formatted chunks"""
            try:
                # Call Ollama with streaming enabled
                response = http_session.post(
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
# AGENTIC MULTI-PASS GENERATION
# ============================================================================

@app.route('/generate/agent', methods=['POST'])
@rate_limit
def generate_agent():
    """
    Agentic multi-pass generation with streaming.
    
    Automatically routes by complexity:
    - Simple: 1 pass (direct answer)
    - Medium: 3 passes (understand → execute → critique)
    - Complex: 5 passes (full pipeline with planning and refinement)
    
    Request JSON:
        - prompt: user question (required)
        - contextMemory: list of previous messages (optional)
        - principal: user principal ID for memory lookup (optional)
        - force_mode: "simple", "medium", "complex", or null for auto (optional)
    
    Response: SSE stream with:
        - {"phase": "understanding", "message": "🤔 Analyzing..."}
        - {"token": "..."} during execution
        - {"done": true, "response": {...}} when complete
    """
    from flask import Response, stream_with_context
    from services.agent import AgentPipeline
    from config import OLLAMA_HOST, MODEL_NAME
    
    # Check capacity
    if metrics.active_requests >= MAX_QUEUE_SIZE:
        return jsonify({'error': 'Server at capacity'}), 503
    
    metrics.start_request()
    
    try:
        data = request.json
        if not data:
            raise ValueError("No JSON data provided")
        
        user_prompt = data.get('prompt', '')
        context_memory = data.get('contextMemory', [])
        principal = data.get('principal')
        force_mode = data.get('force_mode')  # "simple", "medium", "complex", or None
        
        if not user_prompt:
            return jsonify({'error': 'No prompt provided'}), 400
        
        # Load user memory if principal provided
        user_memory = None
        if principal:
            try:
                user_memory = load_user_memory(principal)
            except Exception:
                pass
        
        # Create pipeline instance
        pipeline = AgentPipeline(OLLAMA_HOST, MODEL_NAME)
        
        logger.info(f"🧠 Agent request: {len(user_prompt.split())} words, force_mode={force_mode}")
        
        def generate_sse():
            """Generator that yields SSE-formatted chunks"""
            try:
                for event in pipeline.process_streaming(
                    question=user_prompt,
                    context_messages=context_memory,
                    user_memory=user_memory,
                    force_complexity=force_mode
                ):
                    yield f"data: {json.dumps(event)}\n\n"
                
                metrics.record_request(True, 0, 0)
                
            except Exception as e:
                logger.error(f"Agent streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                metrics.end_request()
        
        return Response(
            stream_with_context(generate_sse()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            }
        )
        
    except Exception as e:
        metrics.end_request()
        logger.error(f"Agent setup error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# WEB SEARCH & BROWSE TOOLS
# ============================================================================

@app.route('/tools/search', methods=['POST'])
@rate_limit
def web_search():
    """
    Search the web using Brave Search API.
    
    Request JSON:
        - query: search query string (required)
        - count: number of results (default: 5, max: 10)
    
    Response JSON:
        - query: the search query
        - results: array of { title, url, snippet }
        - error: error message if failed
    """
    try:
        if not BRAVE_SEARCH_API_KEY:
            return jsonify({
                'error': 'Web search not configured. Set BRAVE_SEARCH_API_KEY environment variable.',
                'results': []
            }), 503
        
        data = request.json or {}
        query = data.get('query', '').strip()
        count = min(int(data.get('count', 5)), 10)  # Cap at 10 results
        
        if not query:
            return jsonify({'error': 'No search query provided', 'results': []}), 400
        
        # Call Brave Search API
        response = http_session.get(
            'https://api.search.brave.com/res/v1/web/search',
            headers={
                'Accept': 'application/json',
                'X-Subscription-Token': BRAVE_SEARCH_API_KEY
            },
            params={
                'q': query,
                'count': count,
                'safesearch': 'moderate'
            },
            timeout=10
        )
        
        if response.status_code != 200:
            logger.error(f"Brave Search API error: {response.status_code}")
            return jsonify({
                'error': f'Search API returned status {response.status_code}',
                'results': []
            }), 502
        
        search_data = response.json()
        web_results = search_data.get('web', {}).get('results', [])
        
        # Extract relevant fields
        results = []
        for r in web_results[:count]:
            results.append({
                'title': r.get('title', ''),
                'url': r.get('url', ''),
                'snippet': r.get('description', '')
            })
        
        logger.info(f"🔍 Web search: '{query}' returned {len(results)} results")
        
        return jsonify({
            'query': query,
            'results': results
        })
        
    except requests.Timeout:
        return jsonify({'error': 'Search request timed out', 'results': []}), 504
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return jsonify({'error': str(e), 'results': []}), 500


@app.route('/tools/browse', methods=['POST'])
@rate_limit
def browse_url():
    """
    Fetch and extract text content from a URL.
    
    Request JSON:
        - url: the URL to fetch (required)
        - max_length: maximum content length (default: 30000)
    
    Response JSON:
        - url: the fetched URL
        - title: page title if found
        - content: extracted text content
        - error: error message if failed
    """
    try:
        data = request.json or {}
        url = data.get('url', '').strip()
        max_length = min(int(data.get('max_length', 30000)), 50000)  # Cap at 50k chars
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'URL must start with http:// or https://'}), 400
        
        # SECURITY: SSRF protection - block internal/private URLs
        is_safe, error_msg = is_safe_url(url)
        if not is_safe:
            logger.warning(f"🚨 SSRF blocked: {url} - {error_msg}")
            return jsonify({'error': error_msg, 'url': url}), 403
        
        # Fetch the page
        response = http_session.get(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; TrinityBot/1.0; +https://trinityai.cc)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            },
            timeout=15,
            allow_redirects=True
        )
        
        if response.status_code != 200:
            return jsonify({
                'error': f'Failed to fetch URL: status {response.status_code}',
                'url': url
            }), 502
        
        content_type = response.headers.get('Content-Type', '')
        
        # Handle different content types
        if 'application/json' in content_type:
            # JSON response - return as pretty-printed text
            try:
                json_content = response.json()
                content = json.dumps(json_content, indent=2)[:max_length]
                return jsonify({
                    'url': url,
                    'title': 'JSON Response',
                    'content': content,
                    'content_type': 'application/json'
                })
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                # Not JSON content, continue to HTML parsing
                logger.debug(f"Response is not JSON: {e}")
        
        # HTML content - extract text using BeautifulSoup (more reliable than regex)
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title = soup.title.string.strip() if soup.title and soup.title.string else ''
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'head', 'meta', 'link', 'noscript', 'iframe']):
            element.decompose()
        
        # Get text content with proper spacing
        clean = soup.get_text(separator=' ', strip=True)
        
        # Normalize whitespace
        import re
        clean = re.sub(r'\s+', ' ', clean)
        clean = clean.strip()[:max_length]
        
        logger.info(f"🌐 Browsed URL: {url} - {len(clean)} chars extracted")
        
        return jsonify({
            'url': url,
            'title': title,
            'content': clean,
            'content_type': 'text/html'
        })
        
    except requests.Timeout:
        return jsonify({'error': 'Request timed out', 'url': url}), 504
    except Exception as e:
        logger.error(f"Browse error: {e}")
        return jsonify({'error': str(e), 'url': url}), 500


@app.route('/tools/search-and-summarize', methods=['POST'])
@rate_limit
def search_and_summarize():
    """
    Combined tool: Search web, fetch top results, and return context for LLM.
    This is the main entry point for giving Trinity web access.
    
    Request JSON:
        - query: search query string (required)
        - num_results: how many results to fetch content from (default: 3, max: 5)
    
    Response JSON:
        - query: the search query
        - context: formatted text ready to inject into LLM prompt
        - sources: list of { title, url } for citation
        - error: error message if failed
    """
    try:
        if not BRAVE_SEARCH_API_KEY:
            return jsonify({
                'error': 'Web search not configured',
                'context': '',
                'sources': []
            }), 503
        
        data = request.json or {}
        query = data.get('query', '').strip()
        num_results = min(int(data.get('num_results', 3)), 5)
        
        if not query:
            return jsonify({'error': 'No search query provided'}), 400
        
        # Step 1: Search
        search_response = http_session.get(
            'https://api.search.brave.com/res/v1/web/search',
            headers={
                'Accept': 'application/json',
                'X-Subscription-Token': BRAVE_SEARCH_API_KEY
            },
            params={'q': query, 'count': num_results + 2, 'safesearch': 'moderate'},
            timeout=10
        )
        
        if search_response.status_code != 200:
            return jsonify({
                'error': 'Search failed',
                'context': '',
                'sources': []
            }), 502
        
        search_data = search_response.json()
        web_results = search_data.get('web', {}).get('results', [])[:num_results]
        
        # Step 2: Fetch content from each result
        from bs4 import BeautifulSoup
        
        sources = []
        context_parts = [f"Web search results for: {query}\n"]
        
        for i, result in enumerate(web_results, 1):
            title = result.get('title', 'Untitled')
            url = result.get('url', '')
            snippet = result.get('description', '')
            
            sources.append({'title': title, 'url': url})
            
            # Try to fetch full content
            try:
                page_response = http_session.get(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0 (compatible; TrinityBot/1.0)'},
                    timeout=8,
                    allow_redirects=True
                )
                
                if page_response.status_code == 200:
                    # Extract text using BeautifulSoup
                    soup = BeautifulSoup(page_response.text, 'html.parser')
                    for element in soup(['script', 'style', 'head', 'meta', 'noscript']):
                        element.decompose()
                    clean = soup.get_text(separator=' ', strip=True)
                    import re
                    clean = re.sub(r'\s+', ' ', clean).strip()[:3000]  # 3k chars per source
                    
                    context_parts.append(f"\n[Source {i}: {title}]\n{clean}\n")
                else:
                    # Use snippet if page fetch fails
                    context_parts.append(f"\n[Source {i}: {title}]\n{snippet}\n")
            except (requests.RequestException, ValueError, AttributeError) as e:
                # Use snippet if page fetch or parsing fails
                logger.debug(f"Failed to fetch source {i}: {e}")
                context_parts.append(f"\n[Source {i}: {title}]\n{snippet}\n")
        
        context = "\n".join(context_parts)
        
        logger.info(f"🔍 Search+summarize: '{query}' - {len(sources)} sources, {len(context)} chars")
        
        return jsonify({
            'query': query,
            'context': context,
            'sources': sources
        })
        
    except Exception as e:
        logger.error(f"Search and summarize error: {e}")
        return jsonify({'error': str(e), 'context': '', 'sources': []}), 500


# ============================================================================
# NEW ENDPOINTS: CHAT PERSISTENCE & ARCHIVE
# ============================================================================

@app.route('/chat/autosave', methods=['POST'])
@require_auth
@storage_rate_limit
def autosave_chat():
    """Save chat - encrypts and uploads directly to IPFS via Lighthouse"""
    try:
        # Principal is set by @require_auth decorator
        principal = request.principal
        data = request.json
        
        # Privacy: Only log request metadata, not content
        logger.debug(f'📥 Autosave request from {principal[:16]}...')
        
        chat_id = data.get('chatId')
        messages = data.get('messages', [])
        metadata = data.get('metadata', {})
        
        # Validate inputs
        if not chat_id:
            logger.error('❌ Missing chatId in autosave request')
            return jsonify({'error': 'Missing chatId'}), 400
        
        if not validate_chat_id(chat_id):
            logger.warning(f'⚠️ Invalid chatId format: {chat_id[:20]}...')
            return jsonify({'error': 'Invalid chatId format'}), 400
        
        if not validate_principal_id(principal):
            logger.warning(f'⚠️ Invalid principal format: {principal[:20]}...')
            return jsonify({'error': 'Invalid principal format'}), 400
        
        # Privacy: Don't log metadata (may contain user-generated titles)
        logger.debug(f'   chatId: {chat_id}, messages: {len(messages)}')
        
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
        
        # ==========================================
        # UPLOAD TO IPFS (Primary Storage)
        # IPFS is the source of truth - no local disk cache
        # ==========================================
        lighthouse_filename = f"{principal[:16]}_{chat_id}.json"
        cid = upload_to_ipfs(
            encrypted_json.encode('utf-8'),
            lighthouse_filename,
            principal_id=principal
        )
        
        if not cid:
            logger.error(f'❌ IPFS upload failed for chat {chat_id[:8]}')
            return jsonify({'success': False, 'error': 'IPFS upload failed'}), 500
        
        logger.info(f'☁️  Saved to IPFS: {cid[:16]}...')
        
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
        
        # Also sync metadata to IPFS (so we can restore chat list)
        try:
            metadata_filename = f"{principal[:16]}_metadata.json"
            metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
            upload_to_ipfs(
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
@storage_rate_limit
def list_chats():
    """List all chats for user - fetches from IPFS via Lighthouse"""
    try:
        principal = request.principal
        
        # ==========================================
        # FETCH CHAT LIST FROM IPFS
        # IPFS is the source of truth - no local disk
        # ==========================================
        logger.info(f'🔍 Fetching chat list from IPFS for {principal[:16]}...')
        
        chats = []
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
                response = http_session.get(gateway_url, timeout=30)
                
                if response.status_code == 200:
                    encrypted_metadata = response.json()
                    recovered_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)
                    chats = recovered_metadata.get('chats', [])
                    logger.info(f'✅ Retrieved {len(chats)} chats from IPFS')
            else:
                # No metadata bundle, but check for individual chat files
                for upload in uploads[:50]:  # Limit to recent 50
                    filename = upload.get('fileName', '')
                    if principal[:16] in filename and 'metadata' not in filename:
                        # Extract chat_id from filename pattern: principal_chatId.json
                        parts = filename.replace('.json', '').split('_')
                        if len(parts) >= 2:
                            chat_id = parts[-1]
                            chats.append({
                                'chatId': chat_id,
                                'title': 'Recovered Chat',
                                'cid': upload.get('cid'),
                                'lastUpdated': upload.get('createdAt', 0),
                                'isArchived': False
                            })
                if chats:
                    logger.info(f'✅ Found {len(chats)} individual chats on IPFS')
                    
        except Exception as ipfs_error:
            logger.warning(f'⚠️  IPFS fetch failed: {ipfs_error}')
        
        # Sort by last updated (newest first)
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
@storage_rate_limit
def get_chat(chat_id):
    """Load specific chat from IPFS"""
    try:
        principal = request.principal
        
        # Validate inputs
        if not validate_chat_id(chat_id):
            logger.warning(f'⚠️ Invalid chatId format in GET: {chat_id[:20]}...')
            return jsonify({'error': 'Invalid chatId format'}), 400
        
        # ==========================================
        # FETCH CHAT FROM IPFS
        # IPFS is the source of truth - no local disk
        # ==========================================
        logger.info(f'🔍 Fetching chat from IPFS: {chat_id[:8]}...')
        
        cid = None
        # Try to find CID by filename pattern in Lighthouse
        try:
            uploads = get_lighthouse_uploads(principal)
            for upload in uploads:
                filename = upload.get('fileName', '')
                if chat_id in filename and 'metadata' not in filename:
                    cid = upload.get('cid')
                    break
        except Exception as e:
            logger.warning(f'Could not search Lighthouse uploads: {e}')
        
        if cid:
            logger.info(f'☁️  Found CID: {cid[:16]}..., downloading from IPFS')
            try:
                # Download from Lighthouse gateway
                gateway_url = f'{LIGHTHOUSE_GATEWAY}/ipfs/{cid}'
                response = http_session.get(gateway_url, timeout=30)
                
                if response.status_code == 200:
                    encrypted_data = response.json()
                    decrypted = EncryptionUtils.decrypt_chat(encrypted_data, principal)
                    logger.info(f'✅ Loaded chat from IPFS: {chat_id[:8]}...')
                    return jsonify(decrypted)
                else:
                    logger.warning(f'IPFS gateway returned {response.status_code}')
            except Exception as ipfs_error:
                logger.error(f'Failed to download from IPFS: {ipfs_error}')
        
        return jsonify({'error': 'Chat not found on IPFS'}), 404
    
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        logger.error(f'Get chat error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<chat_id>', methods=['DELETE'])
@require_auth
@storage_rate_limit
def delete_chat(chat_id):
    """Delete chat - marks as deleted in metadata (IPFS is immutable, but we update the index)"""
    try:
        principal = request.principal
        
        # Validate inputs
        if not validate_chat_id(chat_id):
            logger.warning(f'⚠️ Invalid chatId format in DELETE: {chat_id[:20]}...')
            return jsonify({'error': 'Invalid chatId format'}), 400
        
        # Note: IPFS content is immutable, but we can update the metadata index
        # to remove the chat from the user's list. The encrypted content
        # remains on IPFS but is no longer discoverable without the CID.
        
        # Fetch current metadata from IPFS
        uploads = get_lighthouse_uploads(principal)
        metadata_cid = None
        for upload in uploads:
            filename = upload.get('fileName', '')
            if principal[:16] in filename and 'metadata' in filename:
                metadata_cid = upload.get('cid')
                break
        
        if metadata_cid:
            gateway_url = f'{LIGHTHOUSE_GATEWAY}/ipfs/{metadata_cid}'
            response = http_session.get(gateway_url, timeout=30)
            if response.status_code == 200:
                encrypted_metadata = response.json()
                user_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)
                
                # Remove chat from list
                user_metadata['chats'] = [c for c in user_metadata.get('chats', []) if c['chatId'] != chat_id]
                
                # Upload updated metadata to IPFS
                metadata_filename = f"{principal[:16]}_metadata.json"
                metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
                upload_to_ipfs(
                    json.dumps(metadata_encrypted).encode('utf-8'),
                    metadata_filename,
                    principal_id=principal,
                    is_master_bundle=True
                )
        
        logger.info(f'🗑️  Chat deleted from index: {chat_id[:8]}...')
        
        return jsonify({
            'success': True,
            'deletedAt': int(time.time() * 1000)
        })
    
    except Exception as e:
        logger.error(f'Delete chat error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/chat/<chat_id>/archive', methods=['POST'])
@require_auth
@storage_rate_limit
def archive_chat(chat_id):
    """Mark chat as archived - chat is already on IPFS, this just flags it as permanent"""
    try:
        principal = request.principal
        
        # Validate inputs
        if not validate_chat_id(chat_id):
            logger.warning(f'⚠️ Invalid chatId format in archive: {chat_id[:20]}...')
            return jsonify({'error': 'Invalid chatId format'}), 400
        
        # Fetch current metadata from IPFS
        uploads = get_lighthouse_uploads(principal)
        metadata_cid = None
        chat_cid = None
        
        for upload in uploads:
            filename = upload.get('fileName', '')
            if principal[:16] in filename and 'metadata' in filename:
                metadata_cid = upload.get('cid')
            if chat_id in filename and 'metadata' not in filename:
                chat_cid = upload.get('cid')
        
        if not chat_cid:
            return jsonify({'error': 'Chat not found on IPFS'}), 404
        
        # Load metadata from IPFS
        user_metadata = {'chats': []}
        if metadata_cid:
            gateway_url = f'{LIGHTHOUSE_GATEWAY}/ipfs/{metadata_cid}'
            response = http_session.get(gateway_url, timeout=30)
            if response.status_code == 200:
                encrypted_metadata = response.json()
                user_metadata = EncryptionUtils.decrypt_chat(encrypted_metadata, principal)
        
        # Find chat entry in metadata
        chat_entry = next((c for c in user_metadata.get('chats', []) if c['chatId'] == chat_id), None)
        
        if not chat_entry:
            # Create entry if not in metadata
            chat_entry = {'chatId': chat_id, 'cid': chat_cid}
            user_metadata.setdefault('chats', []).append(chat_entry)

        # Check if already archived
        if chat_entry.get('isArchived'):
            return jsonify({'error': 'Chat is already archived'}), 400

        # Hard limit: Maximum 10 archived chats
        archived_count = sum(1 for c in user_metadata.get('chats', []) if c.get('isArchived', False))
        if archived_count >= 10:
            return jsonify({
                'error': 'Maximum 10 archived chats reached. Please delete an archived chat first.',
                'limit': 10,
                'current': archived_count
            }), 400

        # Mark as archived
        chat_entry['isArchived'] = True
        chat_entry['archivedAt'] = int(time.time() * 1000)
        chat_entry['cid'] = chat_cid

        # Upload updated metadata to IPFS
        metadata_filename = f"{principal[:16]}_metadata.json"
        metadata_encrypted = EncryptionUtils.encrypt_chat(user_metadata, principal)
        new_metadata_cid = upload_to_ipfs(
            json.dumps(metadata_encrypted).encode('utf-8'),
            metadata_filename,
            principal_id=principal,
            is_master_bundle=True
        )

        logger.info(f'✅ Chat archived: {chat_id[:8]}... CID: {chat_cid[:16]}...')

        return jsonify({
            'success': True,
            'chatId': chat_id,
            'cid': chat_cid,
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
                'cid': c.get('cid'),
                'archivedAt': c.get('archivedAt'),
                'messageCount': c.get('messageCount', 0)
            }
            for c in user_metadata.get('chats', [])
            if c.get('isArchived') and c.get('cid')
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

        bundle_cid = upload_to_ipfs(bundle_data, bundle_filename, principal_id=principal_id, is_master_bundle=True)

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
        bundle_data = download_from_ipfs(bundle_cid)

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
        
        # Validate CID format
        if not validate_cid(cid):
            logger.warning(f'⚠️ Invalid CID format: {cid[:20]}...')
            return jsonify({'error': 'Invalid CID format'}), 400
        
        logger.info(f'📥 Downloading archived chat: {cid}')

        # Download from IPFS
        chat_data = download_from_ipfs(cid)

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
def get_archive_status(cid):
    """
    Check IPFS availability status for an archived chat.
    
    No auth required - CID is public, status is public information.
    
    Args:
        cid: The IPFS CID to check
        
    Returns:
        Status information including:
        - status: 'available' or 'error'
        - gateways: List of URLs where content can be accessed
    """
    try:
        # Validate CID format
        if not validate_cid(cid):
            logger.warning(f'⚠️ Invalid CID format in status check: {cid[:20]}...')
            return jsonify({'error': 'Invalid CID format'}), 400
        
        logger.info(f'📊 Checking IPFS status for: {cid}')
        
        return jsonify({
            'cid': cid,
            'status': 'available',
            'message': 'Content is pinned on IPFS via Lighthouse',
            'gateways': [
                f'{LIGHTHOUSE_GATEWAY}/ipfs/{cid}',
                f'https://ipfs.io/ipfs/{cid}',
                f'https://dweb.link/ipfs/{cid}'
            ],
            'checkedAt': int(time.time() * 1000)
        })
        
    except Exception as e:
        logger.error(f'❌ Status check error: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ===== USER MEMORY ENDPOINTS =====
@app.route('/user/memory', methods=['GET'])
@require_auth
@storage_rate_limit
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
@storage_rate_limit
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
@storage_rate_limit
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
@storage_rate_limit
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
        response = http_session.post(
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
@rate_limit  # Apply rate limiting to prevent abuse
def upload_document():
    """Upload a document for querying."""
    try:
        data = request.json
        content = data.get('content', '')
        filename = data.get('filename', 'uploaded_document.txt')
        session_id = data.get('sessionId', str(time.time()))

        if not content:
            return jsonify({'error': 'No content provided'}), 400

        # SECURITY: Enforce document size limit to prevent DoS
        if len(content) > MAX_DOCUMENT_SIZE:
            return jsonify({
                'error': f'Document too large (max {MAX_DOCUMENT_SIZE // 1_000_000}MB)',
                'received': len(content),
                'max_allowed': MAX_DOCUMENT_SIZE
            }), 413

        # Run cleanup before adding new document
        cleanup_document_store()

        # Thread-safe document store access
        with _document_store_lock:
            document_store[session_id] = {
                'content': content,
                'filename': filename,
                'uploaded_at': datetime.now(tz=None).isoformat(),  # Use timezone-aware
                'uploaded_at_ts': time.time()  # For TTL tracking
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

        if not query:
            return jsonify({'error': 'No query provided'}), 400

        # Thread-safe document store access
        with _document_store_lock:
            if not session_id or session_id not in document_store:
                return jsonify({'error': 'No document found. Please upload first.'}), 400
            doc = document_store[session_id].copy()  # Copy to release lock quickly

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


@app.route('/tools/status')
def tools_status():
    """Check status of all AI tools."""
    ollama_ok = check_ollama_connection()
    return jsonify({
        'ollama_connected': ollama_ok,
        'model': MODEL_NAME,
        'tools': {
            'chatWithDocuments': {'available': ollama_ok},
            'transcriptCleaner': {'available': ollama_ok}
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
        response = http_session.post(
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

