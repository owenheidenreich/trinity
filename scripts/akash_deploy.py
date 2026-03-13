#!/usr/bin/env python3
"""
Akash Deployment Helper for Trinity

Model-first deployment: pick a model, see all available providers, choose one.
Generates SDL dynamically based on model requirements — no hardcoded tier YAMLs.

Usage:
  python3 akash_deploy.py <deploy_dir> <image_tag> [model_or_tier] [additional_akt]

  model_or_tier:
    qwen3:0.6b, qwen3:1.7b, qwen3:4b, qwen3:8b   — Qwen3 family
    qwen2.5:1.5b, qwen2.5:7b                       — Qwen2.5 alternatives
    tier3                                            — Qwen3-Coder-Next 80B MoE (uses static YAML)
    test, production                                 — Legacy aliases (→ qwen3:0.6b, qwen3:8b)
    (omit for interactive selection)
"""

import subprocess
import json
import sys
import time
import tempfile
import os
import re
from pathlib import Path

def load_env_file():
    """Load API keys from .env file"""
    env_values = {}
    script_dir = Path(__file__).parent.absolute()
    env_path = script_dir.parent / '.env'

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_values[key.strip()] = value.strip()
    else:
        print(f"⚠️  Warning: .env file not found at {env_path}")

    return env_values

# Load environment values on module import
ENV_VALUES = load_env_file()

# Confirm API keys are loaded (without revealing them)
if 'LIGHTHOUSE_API_KEY' in ENV_VALUES and 'BRAVE_SEARCH_API_KEY' in ENV_VALUES:
    print(f"✓ API keys loaded from .env (Lighthouse: {ENV_VALUES['LIGHTHOUSE_API_KEY'][:8]}..., Brave: {ENV_VALUES['BRAVE_SEARCH_API_KEY'][:8]}...)")
elif 'LIGHTHOUSE_API_KEY' in ENV_VALUES:
    print(f"✓ Lighthouse API key loaded, Brave API key missing")
elif 'BRAVE_SEARCH_API_KEY' in ENV_VALUES:
    print(f"✓ Brave API key loaded, Lighthouse API key missing")
else:
    print("⚠️  No API keys found in .env file")

# =============================================================================
# CONFIGURATION
# =============================================================================

# RPC nodes with failover (akashnet.net last — often overloaded)
AKASH_RPC_NODES = [
    "https://akash-rpc.polkachu.com:443",
    "https://akash-rpc.publicnode.com:443",
    "https://rpc-akash.ecostake.com:443",
    "https://rpc.akashnet.net:443",
]
AKASH_NODE = AKASH_RPC_NODES[0]  # Will be updated by find_working_rpc()
AKASH_CHAIN_ID = "akashnet-2"
WALLET_NAME = "trinity-wallet"

# Model definitions: what each model needs to run
MODELS = {
    "qwen3:0.6b":   {"vram_min": 1,  "cpu": 4, "ram": "4Gi",  "storage": "8Gi",  "chat_ctx": 2048,  "ingest_ctx": 1024, "gguf_gb": 0.4,  "desc": "Qwen3 0.6B — tiny, fast, basic quality"},
    "qwen3:1.7b":   {"vram_min": 2,  "cpu": 4, "ram": "4Gi",  "storage": "8Gi",  "chat_ctx": 4096,  "ingest_ctx": 2048, "gguf_gb": 1.0,  "desc": "Qwen3 1.7B — good demo quality"},
    "qwen3:4b":     {"vram_min": 4,  "cpu": 4, "ram": "6Gi",  "storage": "10Gi", "chat_ctx": 8192,  "ingest_ctx": 4096, "gguf_gb": 2.5,  "desc": "Qwen3 4B — solid quality"},
    "qwen3:8b":     {"vram_min": 6,  "cpu": 4, "ram": "8Gi",  "storage": "20Gi", "chat_ctx": 40960, "ingest_ctx": 8192, "gguf_gb": 5.0,  "desc": "Qwen3 8B — production quality"},
    "qwen2.5:1.5b": {"vram_min": 2,  "cpu": 4, "ram": "4Gi",  "storage": "8Gi",  "chat_ctx": 4096,  "ingest_ctx": 2048, "gguf_gb": 1.1,  "desc": "Qwen2.5 1.5B — stable, well-tested"},
    "qwen2.5:7b":   {"vram_min": 6,  "cpu": 4, "ram": "8Gi",  "storage": "20Gi", "chat_ctx": 32768, "ingest_ctx": 8192, "gguf_gb": 4.7,  "desc": "Qwen2.5 7B — production alternative"},
}

# GPU models for SDL generation — MUST NOT have duplicates.
# Names must match what providers advertise in capabilities/gpu/vendor/nvidia/model/<name>.
# Queried from live Akash network 2026-03-12.
# NOTE: Akash rejects SDLs with duplicate GPU attribute keys, so each model
# appears exactly ONCE using the name providers actually register with.
SDL_GPUS = {
    # Verified on live network — these names match real provider attributes
    "rtx3080": 10,          # ouroboroz.tech
    "rtx-3070": 8,          # rcelsi-akash (note: hyphenated)
    "3090": 24,             # myceliumnetworks (no "rtx" prefix)
    "4090": 24,             # velascompute, sea.nb (no "rtx" prefix)
    "rtx5090": 32,          # btc.com
    "t4": 16,               # neo.testcoders
    "v100": 16,             # rendertent
    "a4000": 16,            # nebulablock (lowercase)
    "A4000": 16,            # apocasoft (uppercase)
    "a100": 80,             # 2-pcs
    "h100": 80,             # (known but scarce)
    "h200": 140,            # lunarvend
}

# Extended lookup for VRAM info display (not used in SDL generation)
# Includes alternate naming so get_provider_host() can show VRAM for any name
ALL_GPUS = {**SDL_GPUS,
    "rtx3060": 12, "rtx3070": 8, "rtx3090": 24,
    "rtx4060ti": 16, "rtx4070": 12, "rtx4080": 16, "rtx4090": 24,
    "a5000": 24, "a6000": 48, "a40": 48,
    "l4": 24, "l40": 48, "l40s": 48,
}

# Legacy tier aliases → model names
TIER_ALIASES = {
    "test": "qwen3:0.6b",
    "production": "qwen3:8b",
}

# Providers to AVOID - known issues with timeouts, SSL, or reliability
BLOCKED_PROVIDERS = [
    "akash19yhu3jgw8h0320av98h8n5qczje3pj3u9u2amp",  # bdl.computer - times out
    "akash1sjwuwre4qprcaa34f6324yz7m8nn0awvc75gp5",  # quanglong.org - very slow image pulls
    "akash1adyrcsp2ptwd83txgv555eqc0vhfufc37wx040",  # airitdecomp.net - DNS doesn't resolve
    "akash1kqzpqqhm39umt06wu8m4hx63v5hefhrfmjf9dj",  # leet.haus - containers fail to start
    "akash1ggfvyhr9sar4uxjs4hth3p4kzrwk7lysnenj3g",  # ghost provider - bids but never provisions
]

# Provider URIs to AVOID - matched against ingress hostnames
BLOCKED_PROVIDER_URIS = [
    "subangle.com",   # subangle - unreliable
    "leet.haus",      # leet.haus - containers fail to start
]

# =============================================================================
# INFRASTRUCTURE (RPC, wallet, Akash CLI wrappers)
# =============================================================================

def find_working_rpc():
    """Test RPC nodes with a real market query (not just a ping)."""
    global AKASH_NODE
    for node in AKASH_RPC_NODES:
        try:
            result = subprocess.run(
                f"provider-services query market order list --node {node} --limit 1 -o json",
                shell=True, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                AKASH_NODE = node
                print(f"✅ Using RPC: {node}")
                return node
            else:
                print(f"  ⚠️  {node} — query failed")
        except subprocess.TimeoutExpired:
            print(f"  ⚠️  {node} — timeout")
    print("❌ All RPC nodes unreachable!")
    sys.exit(1)

def run_cmd(cmd, capture=True, timeout=120):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True, timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1

def get_wallet_address():
    """Get wallet address"""
    stdout, stderr, code = run_cmd(
        f"provider-services keys show {WALLET_NAME} --keyring-backend os -a 2>/dev/null"
    )
    return stdout.strip() if code == 0 else None

def close_all_active_deployments(wallet_addr):
    """Close ALL active deployments to start fresh"""
    print("Closing all active deployments...")

    stdout, stderr, code = run_cmd(
        f"provider-services query deployment list "
        f"--owner {wallet_addr} --state active "
        f"--node {AKASH_NODE} -o json 2>/dev/null"
    )

    if code != 0:
        print("  ✓ No active deployments found")
        return 0

    try:
        data = json.loads(stdout)
        deployments = data.get("deployments", [])
        closed_count = 0

        for dep in deployments:
            dseq = dep.get("deployment", {}).get("deployment_id", {}).get("dseq", "")
            if not dseq:
                dseq = dep.get("deployment", {}).get("id", {}).get("dseq", "")
            if not dseq:
                continue

            print(f"  Closing deployment {dseq}...")
            run_cmd(
                f"provider-services tx deployment close "
                f"--dseq {dseq} --from {WALLET_NAME} --keyring-backend os "
                f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
                f"--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y 2>&1",
                timeout=30
            )
            closed_count += 1
            time.sleep(2)

        if closed_count > 0:
            print(f"  ✓ Closed {closed_count} deployment(s)")
        else:
            print("  ✓ No active deployments to close")

        return closed_count
    except Exception as e:
        print(f"  Warning: Could not close deployments: {e}")
        return 0

def close_deployment(dseq):
    """Close a deployment"""
    run_cmd(
        f"provider-services tx deployment close --dseq {dseq} "
        f"--from {WALLET_NAME} --keyring-backend os "
        f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
        f"--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 "
        f"--yes 2>/dev/null"
    )

def create_lease(dseq, provider):
    """Create a lease with a provider"""
    stdout, stderr, code = run_cmd(
        f"provider-services tx market lease create "
        f"--dseq {dseq} --gseq 1 --oseq 1 --provider {provider} "
        f"--from {WALLET_NAME} --keyring-backend os "
        f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
        f"--gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt "
        f"--yes 2>&1"
    )
    return code == 0

def get_lease_status(dseq, provider):
    """Get lease status including URI"""
    stdout, stderr, code = run_cmd(
        f"provider-services lease-status "
        f"--dseq {dseq} --provider {provider} "
        f"--from {WALLET_NAME} --keyring-backend os "
        f"--node {AKASH_NODE} 2>/dev/null"
    )
    if code == 0:
        try:
            return json.loads(stdout)
        except:
            pass
    return None

def price_to_monthly(uakt_per_block):
    """Convert uakt per block to monthly cost"""
    akt_per_block = float(uakt_per_block) / 1000000
    daily = akt_per_block * 14400  # ~6 second blocks, ~14400 blocks/day
    monthly = daily * 30
    return monthly

def check_ssl_valid(uri):
    """Check if the provider has a valid SSL certificate"""
    import ssl
    import socket
    try:
        hostname = uri.split('/')[0] if '/' in uri else uri
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                return True
    except:
        return False

def get_provider_host(provider_addr):
    """Look up a provider's host URI and GPU info from the chain.
    Returns (host, gpu_info) tuple.
    """
    stdout, stderr, code = run_cmd(
        f"provider-services query provider get {provider_addr} "
        f"--node {AKASH_NODE} -o json",
        timeout=15
    )
    if code != 0:
        return "unknown", ""
    try:
        data = json.loads(stdout)
        host = data.get("host_uri", "") or data.get("provider", {}).get("host_uri", "")
        host = host.replace("https://", "").replace("http://", "").rstrip("/")

        # Extract GPU model from provider attributes
        # Format: capabilities/gpu/vendor/nvidia/model/<model_name> = true
        gpu_info = ""
        attributes = data.get("attributes", []) or data.get("provider", {}).get("attributes", [])
        for attr in attributes:
            key = attr.get("key", "")
            # Match "capabilities/gpu/vendor/nvidia/model/<name>" (top-level, no sub-paths like /ram/)
            if key.startswith("capabilities/gpu/vendor/") and "/model/" in key:
                parts = key.split("/model/")
                if len(parts) >= 2:
                    model_name = parts[1].split("/")[0]  # strip /ram/... etc
                    if model_name and model_name != "other":
                        gpu_info = model_name.upper()
                        break
            # Some providers use legacy attributes like "hardware-gpu = 3060"
            if key == "hardware-gpu" and attr.get("value", ""):
                gpu_info = attr["value"].upper()
                break

        return host or "unknown", gpu_info
    except:
        return "unknown", ""

# =============================================================================
# SDL GENERATION — build Akash YAML dynamically from model config
# =============================================================================

def generate_sdl(model_name, model_config, image_tag):
    """Generate Akash SDL YAML for a given model.

    Includes ALL nvidia GPUs that meet the model's minimum VRAM requirement.
    This maximizes provider availability.
    """
    # Find all compatible GPUs from SDL_GPUS (no duplicates, verified names only)
    compatible_gpus = sorted(
        [gpu for gpu, vram in SDL_GPUS.items() if vram >= model_config["vram_min"]],
        key=lambda g: SDL_GPUS[g]  # sort by VRAM ascending
    )

    gpu_yaml_lines = "\n".join(f"                - model: {gpu}" for gpu in compatible_gpus)

    # Inject real API keys
    lighthouse_key = ENV_VALUES.get("LIGHTHOUSE_API_KEY", "")
    brave_key = ENV_VALUES.get("BRAVE_SEARCH_API_KEY", "")
    hf_token = ENV_VALUES.get("HF_TOKEN", "")

    sdl = f"""version: "2.0"

services:
  trinity:
    image: gdubx/trinity-inference:{image_tag}
    env:
      - PROVIDER_ID=trinity-{model_name.replace(":", "-")}
      - MODEL_NAME={model_name}
      - MODEL_BACKEND=llama-server
      - LLAMA_SERVER_CHAT_PORT=8081
      - LLAMA_SERVER_INGEST_PORT=8082
      - LLAMA_SERVER_CHAT_CTX={model_config["chat_ctx"]}
      - LLAMA_SERVER_INGEST_CTX={model_config["ingest_ctx"]}
      - CHAT_MODEL={model_name}
      - INGEST_MODEL={model_name}
      - GPU_TYPE=auto
      - NUM_CTX={model_config["chat_ctx"]}
      - CHATS_DIR=/data/chats
      - TZ=UTC
      - MAX_QUEUE_SIZE=5
      - EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
      - RAG_TOP_K=5
      - RAG_CHUNK_SIZE=512
      - RAG_CHUNK_OVERLAP=50
      - WORKING_MEMORY_SIZE=5
      - SEMANTIC_MEMORY_SIZE=8
      - PROFILE_TOKEN_BUDGET=2500
      - PROFILE_MAX_FACTS=15
      - RECENCY_WEIGHT=0.3
      - CODE_EXECUTION_ENABLED=false
      - CODE_EXECUTION_TIMEOUT=5
      - LIGHTHOUSE_API_KEY={lighthouse_key}
      - BRAVE_SEARCH_API_KEY={brave_key}
      - HF_TOKEN={hf_token}
      - DEPLOYMENT_TIER=production
      - DEPLOYMENT_TIER_NAME=Production
      - SESSION_TYPE=community
    expose:
      - port: 8000
        as: 80
        to:
          - global: true
        http_options:
          read_timeout: 60000
          send_timeout: 60000
          max_body_size: 52428800

profiles:
  compute:
    trinity:
      resources:
        cpu:
          units: {model_config["cpu"]}
        memory:
          size: {model_config["ram"]}
        storage:
          - size: {model_config["storage"]}
        gpu:
          units: 1
          attributes:
            vendor:
              nvidia:
{gpu_yaml_lines}

  placement:
    akash:
      pricing:
        trinity:
          denom: uakt
          amount: 100000

deployment:
  trinity:
    akash:
      profile: trinity
      count: 1
"""
    return sdl

def create_deployment_from_sdl(sdl_content, deposit_uakt=500000):
    """Create a deployment from generated SDL content and return DSEQ."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(sdl_content)
        temp_yaml = f.name

    try:
        stdout, stderr, code = run_cmd(
            f"provider-services tx deployment create {temp_yaml} "
            f"--deposit {deposit_uakt}uakt "
            f"--from {WALLET_NAME} --keyring-backend os "
            f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
            f"--gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt "
            f"--yes -o json"
        )

        if code != 0:
            print(f"  ❌ Deployment creation failed (exit code {code})")
            if stdout:
                print(f"  stdout: {stdout[:500]}")
            if stderr:
                print(f"  stderr: {stderr[:500]}")
            return None

        match = re.search(r'dseq[^\d]*(\d+)', stdout)
        if match:
            return int(match.group(1))
        print(f"  ❌ Could not extract DSEQ from output:")
        print(f"  {stdout[:500]}")
        return None
    finally:
        os.unlink(temp_yaml)

def send_manifest_from_sdl(sdl_content, dseq, provider):
    """Send manifest from generated SDL content."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(sdl_content)
        temp_yaml = f.name

    try:
        stdout, stderr, code = run_cmd(
            f"provider-services send-manifest {temp_yaml} "
            f"--dseq {dseq} --provider {provider} "
            f"--from {WALLET_NAME} --keyring-backend os "
            f"--node {AKASH_NODE} 2>&1",
            timeout=60
        )
        return code == 0 and "FAIL" not in stdout
    finally:
        os.unlink(temp_yaml)

# =============================================================================
# LEGACY SUPPORT — tier3 still uses static YAML
# =============================================================================

def create_deployment_from_yaml(yaml_path, image_tag, deposit_uakt=500000):
    """Create a deployment from a static YAML file (for tier3)."""
    with open(yaml_path, 'r') as f:
        yaml_content = f.read()

    yaml_content = re.sub(
        r'gdubx/trinity-inference:[^\s]*',
        f'gdubx/trinity-inference:{image_tag}',
        yaml_content
    )

    # Inject API keys
    for key_name in ['LIGHTHOUSE_API_KEY', 'BRAVE_SEARCH_API_KEY', 'HF_TOKEN']:
        if key_name in ENV_VALUES:
            yaml_content = yaml_content.replace(
                f'- {key_name}=\n',
                f'- {key_name}={ENV_VALUES[key_name]}\n'
            )
            yaml_content = yaml_content.replace(
                f'${{{key_name}}}',
                ENV_VALUES[key_name]
            )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_yaml = f.name

    try:
        stdout, stderr, code = run_cmd(
            f"provider-services tx deployment create {temp_yaml} "
            f"--deposit {deposit_uakt}uakt "
            f"--from {WALLET_NAME} --keyring-backend os "
            f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
            f"--gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt "
            f"--yes -o json"
        )

        if code != 0:
            print(f"  ❌ Deployment creation failed (exit code {code})")
            if stdout:
                print(f"  stdout: {stdout[:500]}")
            if stderr:
                print(f"  stderr: {stderr[:500]}")
            return None

        match = re.search(r'dseq[^\d]*(\d+)', stdout)
        if match:
            return int(match.group(1))
        print(f"  ❌ Could not extract DSEQ from output:")
        print(f"  {stdout[:500]}")
        return None
    finally:
        os.unlink(temp_yaml)

def send_manifest_from_yaml(yaml_path, dseq, provider, image_tag):
    """Send manifest from a static YAML file (for tier3)."""
    with open(yaml_path, 'r') as f:
        yaml_content = f.read()

    yaml_content = re.sub(
        r'gdubx/trinity-inference:[^\s]*',
        f'gdubx/trinity-inference:{image_tag}',
        yaml_content
    )

    for key_name in ['LIGHTHOUSE_API_KEY', 'BRAVE_SEARCH_API_KEY', 'HF_TOKEN']:
        if key_name in ENV_VALUES:
            yaml_content = yaml_content.replace(
                f'- {key_name}=\n',
                f'- {key_name}={ENV_VALUES[key_name]}\n'
            )
            yaml_content = yaml_content.replace(
                f'${{{key_name}}}',
                ENV_VALUES[key_name]
            )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_yaml = f.name

    try:
        stdout, stderr, code = run_cmd(
            f"provider-services send-manifest {temp_yaml} "
            f"--dseq {dseq} --provider {provider} "
            f"--from {WALLET_NAME} --keyring-backend os "
            f"--node {AKASH_NODE} 2>&1",
            timeout=60
        )
        return code == 0 and "FAIL" not in stdout
    finally:
        os.unlink(temp_yaml)

# =============================================================================
# USER INTERACTION — model selection, provider display
# =============================================================================

def select_model():
    """Interactive model selection"""
    model_list = list(MODELS.keys())

    print("\n┌──────────────────────────────────────────────────────────────────────┐")
    print("│                        SELECT MODEL                                │")
    print("├──────────────────────────────────────────────────────────────────────┤")
    for i, (name, cfg) in enumerate(MODELS.items(), 1):
        gguf = cfg["gguf_gb"]
        vram = cfg["vram_min"]
        gpus = sum(1 for v in SDL_GPUS.values() if v >= vram)
        print(f"│  {i}) {name:<14} {gguf:>4.1f}GB  {vram:>2}GB+ VRAM  ({gpus:>2} GPUs match)  │")
        print(f"│     {cfg['desc']:<62}│")
    print("├──────────────────────────────────────────────────────────────────────┤")
    print("│  7) tier3         Qwen3-Coder-Next 80B MoE (static YAML)          │")
    print("└──────────────────────────────────────────────────────────────────────┘")

    while True:
        try:
            choice = input("\nSelect model [1-7] or name (e.g. qwen3:4b): ").strip()

            # Check for tier3
            if choice in ['7', 'tier3']:
                return 'tier3', None

            # Check numeric
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(model_list):
                    name = model_list[idx]
                    return name, MODELS[name]

            # Check direct model name
            if choice in MODELS:
                return choice, MODELS[choice]

            # Check legacy tier aliases
            if choice in TIER_ALIASES:
                name = TIER_ALIASES[choice]
                return name, MODELS[name]

            print(f"  Invalid selection. Enter 1-7 or a model name.")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(1)

def get_bids(wallet_addr, dseq):
    """Get ALL bids for a deployment, sorted by price. No filtering."""
    stdout, stderr, code = run_cmd(
        f"provider-services query market bid list "
        f"--owner {wallet_addr} --dseq {dseq} "
        f"--node {AKASH_NODE} -o json"
    )

    if code != 0:
        print(f"  ❌ Bid query failed (exit code {code})")
        if stderr:
            print(f"  stderr: {stderr[:300]}")
        return []

    try:
        data = json.loads(stdout)
        bids = data.get("bids", [])
        print(f"  📡 Raw bids from chain: {len(bids)}")

        provider_prices = []
        for bid in bids:
            provider = bid.get("bid", {}).get("id", {}).get("provider", "")
            price_str = bid.get("bid", {}).get("price", {}).get("amount", "999999999")
            if not provider:
                continue
            try:
                price = float(price_str)
            except:
                price = 999999999.0
            monthly = price_to_monthly(price)
            provider_prices.append((provider, price, monthly))

        provider_prices.sort(key=lambda x: x[1])

        if provider_prices:
            print(f"  💰 {len(provider_prices)} providers found")
            print(f"  💰 Price range: ${provider_prices[0][2]:.0f} - ${provider_prices[-1][2]:.0f}/mo")

        return provider_prices
    except Exception as e:
        print(f"  Error parsing bids: {e}")
        return []

def display_providers(bids, provider_hosts, provider_gpus):
    """Display all providers with full details. Flag blocked ones but show them."""
    print("\n┌──────────────────────────────────────────────────────────────────────────────────┐")
    print("│                            AVAILABLE PROVIDERS                                  │")
    print("├──────────────────────────────────────────────────────────────────────────────────┤")

    for i, (provider, price, monthly) in enumerate(bids, 1):
        host = provider_hosts.get(provider, "unknown")
        gpu = provider_gpus.get(provider, "GPU")

        # Flag issues but still show the provider
        flags = ""
        if provider in BLOCKED_PROVIDERS:
            flags = " ⛔"
        elif any(blocked in host for blocked in BLOCKED_PROVIDER_URIS):
            flags = " ⚠️"

        print(f"│  {i:>2}) ${monthly:>7.2f}/mo  {gpu:<14} {host:<40}{flags:>3}│")

    print("├──────────────────────────────────────────────────────────────────────────────────┤")
    print("│  ⛔ = known bad provider   ⚠️ = previously unreliable (still selectable)        │")
    print("└──────────────────────────────────────────────────────────────────────────────────┘")

# =============================================================================
# MAIN DEPLOYMENT FLOW
# =============================================================================

def main():
    if len(sys.argv) < 3:
        print("Usage: akash_deploy.py <deploy_dir> <image_tag> [model] [additional_akt]")
        print("  model: qwen3:0.6b, qwen3:1.7b, qwen3:4b, qwen3:8b, qwen2.5:1.5b, qwen2.5:7b, tier3")
        print("  Legacy: 'test' → qwen3:0.6b, 'production' → qwen3:8b")
        sys.exit(1)

    deploy_dir = sys.argv[1]
    image_tag = sys.argv[2]

    # Find a working RPC node
    print("🔍 Testing RPC nodes...")
    find_working_rpc()

    # --- Step 1: Select model ---
    model_arg = sys.argv[3] if len(sys.argv) >= 4 else None

    if model_arg == "tier3":
        # Tier3 uses static YAML — delegate to legacy path
        selected_model = "tier3"
        model_config = None
    elif model_arg and model_arg in MODELS:
        selected_model = model_arg
        model_config = MODELS[model_arg]
    elif model_arg and model_arg in TIER_ALIASES:
        selected_model = TIER_ALIASES[model_arg]
        model_config = MODELS[selected_model]
    elif model_arg:
        print(f"❌ Unknown model '{model_arg}'")
        print(f"   Available: {', '.join(MODELS.keys())}, tier3")
        sys.exit(1)
    else:
        selected_model, model_config = select_model()

    if selected_model == "tier3":
        print(f"\n✅ Using tier3: Qwen3-Coder-Next 80B MoE (static YAML)")
    else:
        compatible_gpu_count = sum(1 for v in SDL_GPUS.values() if v >= model_config["vram_min"])
        print(f"\n✅ Model: {selected_model} — {model_config['desc']}")
        print(f"   GGUF size: {model_config['gguf_gb']:.1f}GB, needs {model_config['vram_min']}GB+ VRAM")
        print(f"   Compatible with {compatible_gpu_count}/{len(SDL_GPUS)} GPU types in SDL")

    # --- Step 2: Parse deposit ---
    additional_akt = 0.0
    if len(sys.argv) >= 5:
        try:
            additional_akt = float(sys.argv[4])
        except ValueError:
            pass

    BASE_DEPOSIT_UAKT = 500000
    additional_uakt = int(additional_akt * 1000000)
    deposit_uakt = BASE_DEPOSIT_UAKT + additional_uakt
    total_akt = deposit_uakt / 1000000

    if additional_akt > 0:
        print(f"💰 Escrow deposit: {total_akt:.1f} AKT (0.5 base + {additional_akt:.1f} additional)")
    else:
        print(f"💰 Escrow deposit: {total_akt:.1f} AKT (base minimum)")

    # --- Step 3: Generate SDL or use static YAML ---
    if selected_model == "tier3":
        yaml_path = os.path.join(deploy_dir, "akash", "deploy-tier3.yaml")
        if not os.path.exists(yaml_path):
            print(f"❌ YAML file not found: {yaml_path}")
            sys.exit(1)
        sdl_content = None  # Signal to use YAML path
        model_desc = "Qwen3-Coder-Next 80B MoE"
    else:
        sdl_content = generate_sdl(selected_model, model_config, image_tag)
        model_desc = model_config["desc"]

        # Show the generated GPU list (SDL_GPUS only — what actually goes in the SDL)
        compatible_gpus = sorted(
            [gpu for gpu, vram in SDL_GPUS.items() if vram >= model_config["vram_min"]],
            key=lambda g: SDL_GPUS[g]
        )
        print(f"\n📋 SDL generated — accepting GPUs: {', '.join(compatible_gpus)}")

    # --- Step 4: Get wallet and clean up ---
    print(f"\n🔍 FINDING PROVIDERS")
    print("=" * 60)

    wallet_addr = get_wallet_address()
    if not wallet_addr:
        print("❌ Could not get wallet address")
        sys.exit(1)

    print(f"Wallet: {wallet_addr}")
    close_all_active_deployments(wallet_addr)

    # --- Step 5: Create deployment ---
    print(f"\nCreating deployment for {model_desc}...", end=" ", flush=True)

    if sdl_content:
        dseq = create_deployment_from_sdl(sdl_content, deposit_uakt)
    else:
        dseq = create_deployment_from_yaml(yaml_path, image_tag, deposit_uakt)

    if not dseq:
        print("FAILED")
        print("❌ Could not create deployment")
        sys.exit(1)

    print(f"DSEQ {dseq}")

    # --- Step 6: Wait for bids ---
    print(f"\n⏳ Waiting for provider bids (30 seconds)...")
    time.sleep(30)

    print("Fetching bids...")
    bids = get_bids(wallet_addr, dseq)

    if not bids:
        print("\n❌ No providers bid on this deployment!")
        print("   Possible causes:")
        print("   - No providers have GPUs matching the SDL requirements")
        print("   - All providers are at capacity")
        print("   - Network congestion")
        print("   Try a smaller model (fewer GPU requirements = more providers)")
        close_deployment(dseq)
        sys.exit(1)

    # --- Step 7: Look up provider details ---
    print("\n📡 Looking up provider details...")
    provider_hosts = {}
    provider_gpus = {}
    for provider, price, monthly in bids:
        host, gpu_info = get_provider_host(provider)
        provider_hosts[provider] = host
        provider_gpus[provider] = gpu_info or "GPU"

    # --- Step 8: Display ALL providers (no filtering) ---
    display_providers(bids, provider_hosts, provider_gpus)

    # --- Step 9: User selects provider ---
    print(f"\nSelect a provider [1-{len(bids)}]: ", end="", flush=True)
    try:
        choice = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. Closing deployment...")
        close_deployment(dseq)
        sys.exit(1)

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(bids)):
            print(f"Invalid selection. Closing deployment...")
            close_deployment(dseq)
            sys.exit(1)
    except ValueError:
        print(f"Invalid input. Closing deployment...")
        close_deployment(dseq)
        sys.exit(1)

    selected_provider, selected_price, selected_monthly = bids[idx]
    selected_host = provider_hosts.get(selected_provider, "unknown")
    selected_gpu = provider_gpus.get(selected_provider, "GPU")

    # Warn about known-bad providers but let user proceed
    if selected_provider in BLOCKED_PROVIDERS:
        print(f"\n  ⛔ WARNING: This provider has known issues!")
        try:
            confirm = input("  Continue anyway? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            confirm = "n"
        if confirm != "y":
            print("  Cancelled. Closing deployment...")
            close_deployment(dseq)
            sys.exit(1)

    print(f"\n✓ Selected: {selected_host} ({selected_gpu}, ${selected_monthly:.2f}/mo)")

    # --- Step 10: Create lease ---
    print("\n🔗 CONNECTING TO PROVIDER")
    print("=" * 60)

    print("  Creating lease...", end=" ", flush=True)
    if not create_lease(dseq, selected_provider):
        print("FAILED")
        print("  ❌ Could not create lease with this provider")
        print("  Closing deployment...")
        close_deployment(dseq)
        sys.exit(1)
    print("OK")

    time.sleep(3)

    # --- Step 11: Send manifest ---
    print("  Sending manifest...", end=" ", flush=True)
    if sdl_content:
        manifest_ok = send_manifest_from_sdl(sdl_content, dseq, selected_provider)
    else:
        manifest_ok = send_manifest_from_yaml(yaml_path, dseq, selected_provider, image_tag)

    if not manifest_ok:
        print("FAILED (timeout or rejected)")
        print("  ❌ Provider rejected the manifest or timed out")
        print("  Closing deployment...")
        close_deployment(dseq)
        sys.exit(1)
    print("OK")

    # --- Step 12: Wait for container ---
    # Estimate wait time based on model size
    if selected_model == "tier3":
        max_wait = 1800  # 30 min — 48GB split GGUF
    else:
        gguf_gb = model_config["gguf_gb"]
        if gguf_gb <= 1.5:
            max_wait = 300   # 5 min for small models
        elif gguf_gb <= 5:
            max_wait = 600   # 10 min for medium models
        else:
            max_wait = 900   # 15 min for large models

    print(f"  Waiting for container (up to {max_wait//60} min for {selected_model})...")
    uri = None
    container_ready = False
    start_time = time.time()

    for i in range(max_wait // 10):
        time.sleep(10)
        elapsed = int(time.time() - start_time)

        if elapsed % 30 == 0:
            print(f"    [{elapsed//60}m {elapsed%60}s] Still waiting...")

        status = get_lease_status(dseq, selected_provider)
        if status:
            try:
                services = status.get("services", {})
                for svc_name, svc_info in services.items():
                    uris = svc_info.get("uris", [])
                    available = svc_info.get("available_replicas", 0)

                    if uris and not uri:
                        uri = uris[0]
                        print(f"\n    URI assigned: {uri}")
                        print(f"    Waiting for container to be ready (available={available})...")

                    if uris and available >= 1:
                        uri = uris[0]
                        container_ready = True
                        break
            except:
                pass

            if container_ready:
                break
        else:
            print(".", end="", flush=True)

    if not (uri and container_ready):
        print(f"\n  ❌ Container didn't become ready within {max_wait//60} minutes")
        print(f"  Closing deployment...")
        close_deployment(dseq)
        sys.exit(1)

    print(f" READY!")

    # --- Step 13: Check SSL and output result ---
    print(f"\n  Checking SSL certificate...")
    ssl_valid = check_ssl_valid(uri)
    if ssl_valid:
        print(f"  ✅ SSL valid — using HTTPS")
        full_url = f"https://{uri}"
    else:
        print(f"  ⚠️  SSL invalid — using HTTP")
        full_url = f"http://{uri}"

    print(f"\n" + "=" * 60)
    print(f"✅ DEPLOYMENT SUCCESSFUL!")
    print(f"=" * 60)
    print(f"   Model:    {selected_model} — {model_desc}")
    print(f"   DSEQ:     {dseq}")
    print(f"   Provider: {selected_host} ({selected_gpu})")
    print(f"   URI:      {uri}")
    print(f"   URL:      {full_url}")
    print(f"   Cost:     ${selected_monthly:.2f}/mo")

    # Output for shell script to parse
    print(f"\n__RESULT__")
    print(f"TIER={selected_model}")
    print(f"TIER_DESC={selected_model} — {model_desc}")
    print(f"DSEQ={dseq}")
    print(f"PROVIDER={selected_provider}")
    print(f"URI={uri}")
    print(f"URL={full_url}")
    print(f"COST=${selected_monthly:.2f}/mo")
    sys.exit(0)

if __name__ == "__main__":
    main()
