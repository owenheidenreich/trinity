#!/usr/bin/env python3
"""
Akash Deployment Helper for Trinity
Handles: tier selection, provider discovery, lease creation, manifest sending

Usage:
  python3 akash_deploy.py <deploy_dir> <image_tag> [tier]
  
  tier: 1 (TinyLlama), 2 (Llama 8B), 3 (Qwen 72B)
        If not specified, prompts for selection
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

# Configuration
AKASH_NODE = "https://rpc.akashnet.net:443"
AKASH_CHAIN_ID = "akashnet-2"
WALLET_NAME = "trinity-wallet"

# Tier definitions
TIERS = {
    1: {"yaml": "deploy-tier1-basic.yaml", "desc": "TinyLlama 1.1B (Testing)", "cost": "~$25/mo"},
    2: {"yaml": "deploy-tier2-balanced.yaml", "desc": "Qwen 2.5 3B (Fast & Smart)", "cost": "~$30/mo"},
    3: {"yaml": "deploy-tier3-complex.yaml", "desc": "Qwen 2.5 72B (Intelligence)", "cost": "~$200/mo"},
}

# Minimum price thresholds per tier (below this = hardware too weak)
# These are based on typical GPU provider pricing on Akash
MIN_PRICE_MONTHLY = {
    1: 5,     # TinyLlama - can run on anything
    2: 5,     # Qwen 14B - P40 at $65/mo works great!
    3: 80,    # Qwen 72B - needs serious hardware
}

# Providers to AVOID - known issues with timeouts, SSL, or reliability
BLOCKED_PROVIDERS = [
    "akash19yhu3jgw8h0320av98h8n5qczje3pj3u9u2amp",  # bdl.computer - times out
    "akash1sjwuwre4qprcaa34f6324yz7m8nn0awvc75gp5",  # quanglong.org - very slow image pulls
    "akash1adyrcsp2ptwd83txgv555eqc0vhfufc37wx040",  # airitdecomp.net - DNS doesn't resolve
]

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
    
    # Get all active deployments
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
            # Try both JSON paths (API changed between versions)
            dseq = dep.get("deployment", {}).get("deployment_id", {}).get("dseq", "")
            if not dseq:
                dseq = dep.get("deployment", {}).get("id", {}).get("dseq", "")
            
            if not dseq:
                continue
            
            print(f"  Closing deployment {dseq}...")
            result = run_cmd(
                f"provider-services tx deployment close "
                f"--dseq {dseq} --from {WALLET_NAME} --keyring-backend os "
                f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
                f"--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y 2>&1",
                timeout=30
            )
            closed_count += 1
            time.sleep(2)  # Brief delay between closures
        
        if closed_count > 0:
            print(f"  ✓ Closed {closed_count} deployment(s)")
        else:
            print("  ✓ No active deployments to close")
        
        return closed_count
    except Exception as e:
        print(f"  Warning: Could not close deployments: {e}")
        return 0

def cleanup_orphaned_deployments(wallet_addr, keep_dseq=None):
    """Close any deployments without active leases to recover escrow funds"""
    print("Checking for orphaned deployments...")
    
    # Get all active deployments
    stdout, stderr, code = run_cmd(
        f"provider-services query deployment list "
        f"--owner {wallet_addr} --state active "
        f"--node {AKASH_NODE} -o json 2>/dev/null"
    )
    
    if code != 0:
        return 0
    
    try:
        data = json.loads(stdout)
        deployments = data.get("deployments", [])
        closed_count = 0
        
        for dep in deployments:
            # Try both JSON paths (API changed between versions)
            dseq = dep.get("deployment", {}).get("deployment_id", {}).get("dseq", "")
            if not dseq:
                dseq = dep.get("deployment", {}).get("id", {}).get("dseq", "")
            
            if not dseq or (keep_dseq and str(dseq) == str(keep_dseq)):
                continue
            
            # Check if this deployment has any active leases
            lease_stdout, _, lease_code = run_cmd(
                f"provider-services query market lease list "
                f"--owner {wallet_addr} --dseq {dseq} "
                f"--node {AKASH_NODE} -o json 2>/dev/null"
            )
            
            has_active_lease = False
            if lease_code == 0:
                try:
                    lease_data = json.loads(lease_stdout)
                    leases = lease_data.get("leases", [])
                    for lease in leases:
                        state = lease.get("lease", {}).get("state", "")
                        if state == "active":
                            has_active_lease = True
                            break
                except:
                    pass
            
            if not has_active_lease:
                print(f"  Closing orphaned deployment {dseq}...")
                run_cmd(
                    f"provider-services tx deployment close "
                    f"--dseq {dseq} --from {WALLET_NAME} --keyring-backend os "
                    f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
                    f"--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 -y 2>&1",
                    timeout=30
                )
                closed_count += 1
                time.sleep(2)  # Brief delay between closures
        
        if closed_count > 0:
            print(f"  ✓ Closed {closed_count} orphaned deployment(s), recovered ~{closed_count * 0.5:.1f} AKT")
        else:
            print("  ✓ No orphaned deployments found")
        
        return closed_count
    except Exception as e:
        print(f"  Warning: Could not check for orphaned deployments: {e}")
        return 0

def inject_env_values(yaml_content):
    """Inject API keys from .env into YAML content"""
    # Replace empty env vars or ${VAR} placeholders with actual values from .env
    if 'LIGHTHOUSE_API_KEY' in ENV_VALUES:
        # Handle both formats: empty value and ${VAR} placeholder
        yaml_content = yaml_content.replace(
            '- LIGHTHOUSE_API_KEY=\n',
            f'- LIGHTHOUSE_API_KEY={ENV_VALUES["LIGHTHOUSE_API_KEY"]}\n'
        )
        yaml_content = yaml_content.replace(
            '${LIGHTHOUSE_API_KEY}',
            ENV_VALUES['LIGHTHOUSE_API_KEY']
        )
    if 'BRAVE_SEARCH_API_KEY' in ENV_VALUES:
        yaml_content = yaml_content.replace(
            '- BRAVE_SEARCH_API_KEY=\n',
            f'- BRAVE_SEARCH_API_KEY={ENV_VALUES["BRAVE_SEARCH_API_KEY"]}\n'
        )
        yaml_content = yaml_content.replace(
            '${BRAVE_SEARCH_API_KEY}',
            ENV_VALUES['BRAVE_SEARCH_API_KEY']
        )
    return yaml_content

def create_deployment(yaml_path, image_tag):
    """Create a deployment and return DSEQ"""
    # Create temp YAML with updated image tag
    with open(yaml_path, 'r') as f:
        yaml_content = f.read()

    # Replace any image tag with the new one
    yaml_content = re.sub(
        r'gdubx/trinity-inference:[^\s]*',
        f'gdubx/trinity-inference:{image_tag}',
        yaml_content
    )

    # SECURITY: Inject API keys from .env file
    yaml_content = inject_env_values(yaml_content)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_yaml = f.name
    
    try:
        stdout, stderr, code = run_cmd(
            f"provider-services tx deployment create {temp_yaml} "
            f"--from {WALLET_NAME} --keyring-backend os "
            f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
            f"--gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt "
            f"--yes -o json 2>&1"
        )
        
        # Extract DSEQ from output
        match = re.search(r'dseq[^\d]*(\d+)', stdout)
        if match:
            return int(match.group(1))
        return None
    finally:
        os.unlink(temp_yaml)

def get_bids(wallet_addr, dseq, tier=2):
    """Get bids for a deployment, sorted by price (cheapest first)"""
    stdout, stderr, code = run_cmd(
        f"provider-services query market bid list "
        f"--owner {wallet_addr} --dseq {dseq} "
        f"--node {AKASH_NODE} -o json 2>/dev/null"
    )
    
    if code != 0:
        return []
    
    try:
        data = json.loads(stdout)
        bids = data.get("bids", [])
        
        # Get minimum price for this tier
        min_price = MIN_PRICE_MONTHLY.get(tier, 20)
        
        # Extract all providers with prices
        provider_prices = []
        for bid in bids:
            provider = bid.get("bid", {}).get("id", {}).get("provider", "")
            price_str = bid.get("bid", {}).get("price", {}).get("amount", "999999999")
            if provider:
                # Skip blocked providers
                if provider in BLOCKED_PROVIDERS:
                    continue
                    
                try:
                    price = float(price_str)
                except:
                    price = 999999999.0
                
                monthly = price_to_monthly(price)
                provider_prices.append((provider, price, monthly))
        
        # Sort by price (cheapest first)
        provider_prices.sort(key=lambda x: x[1])
        
        if provider_prices:
            print(f"  📊 Found {len(provider_prices)} providers (sorted cheapest → expensive)")
            print(f"  💰 Price range: ${provider_prices[0][2]:.0f} - ${provider_prices[-1][2]:.0f}/mo")
            print(f"  🎯 Minimum spec threshold for Tier {tier}: ${min_price}/mo")
        
        # Return all bids - filtering happens during selection with proper messages
        return [(p[0], p[1], p[2]) for p in provider_prices]
    except Exception as e:
        print(f"  Error parsing bids: {e}")
        return []

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

def send_manifest(yaml_path, dseq, provider, image_tag):
    """Send manifest to provider"""
    # Create temp YAML with updated image tag
    with open(yaml_path, 'r') as f:
        yaml_content = f.read()

    yaml_content = re.sub(
        r'gdubx/trinity-inference:[^\s]*',
        f'gdubx/trinity-inference:{image_tag}',
        yaml_content
    )

    # SECURITY: Inject API keys from .env file
    yaml_content = inject_env_values(yaml_content)

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

def close_deployment(dseq):
    """Close a deployment"""
    run_cmd(
        f"provider-services tx deployment close --dseq {dseq} "
        f"--from {WALLET_NAME} --keyring-backend os "
        f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
        f"--gas-prices 0.025uakt --gas auto --gas-adjustment 1.5 "
        f"--yes 2>/dev/null"
    )

def check_ssl_valid(uri):
    """Check if the provider has a valid SSL certificate"""
    import ssl
    import socket
    
    try:
        # Parse the URI to get hostname
        hostname = uri.split('/')[0] if '/' in uri else uri
        
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                # If we get here, SSL is valid
                return True
    except ssl.SSLCertVerificationError:
        return False
    except ssl.SSLError:
        return False
    except Exception as e:
        # Connection refused, timeout, etc - assume no valid SSL
        return False

def close_lease(dseq, provider):
    """Close a specific lease"""
    run_cmd(
        f"provider-services tx market lease close "
        f"--dseq {dseq} --gseq 1 --oseq 1 --provider {provider} "
        f"--from {WALLET_NAME} --keyring-backend os "
        f"--node {AKASH_NODE} --chain-id {AKASH_CHAIN_ID} "
        f"--gas auto --gas-adjustment 1.5 --gas-prices 0.025uakt "
        f"--yes 2>/dev/null"
    )

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
    # ~6 second blocks, ~14400 blocks/day
    daily = akt_per_block * 14400
    monthly = daily * 30
    return monthly

def select_tier():
    """Interactive tier selection"""
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│                    SELECT DEPLOYMENT TIER                    │")
    print("├─────────────────────────────────────────────────────────────┤")
    print("│  1) TinyLlama 1.1B  - Testing (~$25/mo)                     │")
    print("│  2) Qwen 2.5 3B     - Fast & Smart (~$30/mo)                │")
    print("│  3) Qwen 2.5 72B    - Intelligence (~$200/mo)               │")
    print("└─────────────────────────────────────────────────────────────┘")
    
    while True:
        try:
            choice = input("\nSelect tier [1/2/3]: ").strip()
            if choice in ['1', '2', '3']:
                return int(choice)
            print("Please enter 1, 2, or 3")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(1)

def main():
    if len(sys.argv) < 3:
        print("Usage: akash_deploy.py <deploy_dir> <image_tag> [tier]")
        print("  tier: 1 (TinyLlama), 2 (Llama 8B), 3 (Qwen 72B)")
        sys.exit(1)
    
    deploy_dir = sys.argv[1]
    image_tag = sys.argv[2]
    
    # Get tier from argument or prompt
    if len(sys.argv) >= 4 and sys.argv[3] in ['1', '2', '3']:
        selected_tier = int(sys.argv[3])
        print(f"\n✅ Using Tier {selected_tier}: {TIERS[selected_tier]['desc']}")
    else:
        selected_tier = select_tier()
        print(f"\n✅ Selected Tier {selected_tier}: {TIERS[selected_tier]['desc']}")
    
    tier_info = TIERS[selected_tier]
    yaml_path = os.path.join(deploy_dir, "akash", tier_info["yaml"])
    
    if not os.path.exists(yaml_path):
        print(f"❌ YAML file not found: {yaml_path}")
        sys.exit(1)
    
    print(f"\n🔍 FINDING PROVIDERS FOR TIER {selected_tier}")
    print("=" * 60)
    
    wallet_addr = get_wallet_address()
    if not wallet_addr:
        print("❌ Could not get wallet address")
        sys.exit(1)
    
    print(f"Wallet: {wallet_addr}")
    
    # Close ALL active deployments to start fresh
    close_all_active_deployments(wallet_addr)
    
    # Create deployment for selected tier
    print(f"\nCreating deployment for {tier_info['desc']}...", end=" ", flush=True)
    dseq = create_deployment(yaml_path, image_tag)
    
    if not dseq:
        print("FAILED")
        print("❌ Could not create deployment")
        sys.exit(1)
    
    print(f"DSEQ {dseq}")
    
    # Wait for bids
    print(f"\n⏳ Waiting for provider bids (25 seconds)...")
    time.sleep(25)
    
    # Fetch bids
    print("Fetching bids...", end=" ", flush=True)
    bids = get_bids(wallet_addr, dseq, selected_tier)
    print(f"found {len(bids)} qualifying provider(s)")
    
    if not bids:
        print("\n❌ No providers available for this tier!")
        print("   This could mean:")
        print("   - No providers have matching GPU resources")
        print("   - Network congestion")
        print("   - Try a different tier or wait a few minutes")
        close_deployment(dseq)
        sys.exit(1)
    
    # Display available providers sorted by price
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│                  AVAILABLE PROVIDERS                         │")
    print("├─────────────────────────────────────────────────────────────┤")
    for i, (provider, price, monthly) in enumerate(bids[:8], 1):  # Show top 8
        print(f"│  {i}. ${monthly:>6.2f}/mo - {provider[:35]}...│")
    print("└─────────────────────────────────────────────────────────────┘")
    
    # Try each provider until one works
    print("\n🔗 CONNECTING TO PROVIDER")
    print("=" * 60)
    
    # Track providers that fail during this session
    skip_providers = []
    min_price = MIN_PRICE_MONTHLY.get(selected_tier, 20)
    
    for provider, price, monthly in bids:
        if provider in skip_providers:
            print(f"\nSkipping previously failed provider: {provider[:30]}...")
            continue
        
        # Check minimum spec threshold
        if monthly < min_price:
            print(f"\n⚠️  Skipping {provider[:35]}...")
            print(f"    └─ Specs too low (${monthly:.0f}/mo < ${min_price}/mo minimum for Tier {selected_tier})")
            continue
            
        print(f"\n✓ Trying: {provider[:40]}...")
        print(f"  Price: ${monthly:.2f}/mo (meets ${min_price}/mo minimum)")
        
        # Create lease
        print("  Creating lease...", end=" ", flush=True)
        if not create_lease(dseq, provider):
            print("FAILED")
            continue
        print("OK")
        
        time.sleep(3)
        
        # Send manifest
        print("  Sending manifest...", end=" ", flush=True)
        if not send_manifest(yaml_path, dseq, provider, image_tag):
            print("FAILED (timeout or rejected)")
            print("  Closing lease and deployment (need to retry from scratch)...")
            close_deployment(dseq)
            # Retry with a new deployment, skipping this provider
            print(f"\n  Retrying with new deployment, skipping {provider[:30]}...")
            dseq = create_deployment(yaml_path, image_tag)
            if not dseq:
                print("  ❌ Failed to create new deployment")
                sys.exit(1)
            print(f"  New DSEQ: {dseq}")
            time.sleep(20)  # Wait for bids on new deployment
            skip_providers.append(provider)  # Don't try this provider again
            bids = get_bids(wallet_addr, dseq, selected_tier)
            bids = [(p, pr, m) for p, pr, m in bids if p not in skip_providers]
            if not bids:
                print("  ❌ No more providers available")
                close_deployment(dseq)
                sys.exit(1)
            continue
        print("OK")
        
        # Wait for container - much longer timeout for Tier 3 (72B model)
        # Tier 3 can take 15-20+ minutes to pull the model on first deploy
        if selected_tier == 1:
            max_wait = 180   # 3 min for TinyLlama
        elif selected_tier == 2:
            max_wait = 420   # 7 min for Llama 8B  
        else:
            max_wait = 1200  # 20 min for Qwen 72B (it's huge!)
        
        print(f"  Waiting for container (up to {max_wait//60} min for Tier {selected_tier})...")
        uri = None
        start_time = time.time()
        check_count = 0
        for i in range(max_wait // 10):  # Check every 10 seconds
            time.sleep(10)
            check_count += 1
            elapsed = int(time.time() - start_time)
            
            # Show progress every 30 seconds
            if elapsed % 30 == 0:
                print(f"    [{elapsed//60}m {elapsed%60}s] Still waiting for container...")
            
            status = get_lease_status(dseq, provider)
            if status:
                # Try to find URI in forwarded_ports
                try:
                    services = status.get("services", {})
                    for svc_name, svc_info in services.items():
                        uris = svc_info.get("uris", [])
                        if uris:
                            uri = uris[0]
                            break
                except:
                    pass
                
                if uri:
                    break
            # Print progress every 30 seconds
            if check_count % 6 == 0:
                print(f" [{elapsed}s]", end="", flush=True)
            else:
                print(".", end="", flush=True)
        
        if uri:
            print(f" READY!")
            
            # Check SSL certificate validity
            print(f"\n  Checking SSL certificate...")
            ssl_valid = check_ssl_valid(uri)
            if ssl_valid:
                print(f"  ✅ SSL certificate valid - using HTTPS")
                full_url = f"https://{uri}"
            else:
                print(f"  ⚠️  SSL certificate invalid - using HTTP")
                full_url = f"http://{uri}"
            
            print(f"\n" + "=" * 60)
            print(f"✅ DEPLOYMENT SUCCESSFUL!")
            print(f"=" * 60)
            print(f"   Tier:     {TIERS[selected_tier]['desc']}")
            print(f"   DSEQ:     {dseq}")
            print(f"   Provider: {provider}")
            print(f"   URI:      {uri}")
            print(f"   URL:      {full_url}")
            print(f"   Cost:     ${monthly:.2f}/mo")
            
            # Output for shell script to parse
            print(f"\n__RESULT__")
            print(f"TIER={selected_tier}")
            print(f"DSEQ={dseq}")
            print(f"PROVIDER={provider}")
            print(f"URI={uri}")
            print(f"URL={full_url}")
            print(f"COST=${monthly:.2f}/mo")
            sys.exit(0)
        else:
            print(" TIMEOUT - container didn't become ready")
            # Continue to next provider
    
    print("\n❌ All providers failed")
    close_deployment(dseq)
    sys.exit(1)

if __name__ == "__main__":
    main()
