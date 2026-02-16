"""
Trinity Backend - Akash Network Service
Functions for interacting with Akash blockchain APIs
"""

import logging
import os
import time
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
AKASH_WALLET_ADDRESS = os.getenv(
    "AKASH_WALLET_ADDRESS", "akash155hphg6qyy3vtr584p38wlngtqxzdr0l6jutmp"
)
AKASH_RPC_NODE = os.getenv("AKASH_RPC_NODE", "https://rpc.akashnet.net:443")

# ICP canister IDs
ICP_BACKEND_CANISTER = os.getenv("ICP_BACKEND_CANISTER", "au5zq-2qaaa-aaaal-qtowa-cai")
ICP_FRONTEND_CANISTER = os.getenv("ICP_FRONTEND_CANISTER", "zc67k-kiaaa-aaaal-qtmiq-cai")

# Deployment info (set via YAML env vars during deployment)
DEPLOYMENT_TIER = os.getenv("DEPLOYMENT_TIER", "production")
DEPLOYMENT_TIER_NAME = os.getenv("DEPLOYMENT_TIER_NAME", "Production")
HOURLY_COST_AKT = float(os.getenv("HOURLY_COST_AKT", "0.15"))
DAILY_COST_AKT = float(os.getenv("DAILY_COST_AKT", "3.6"))
SESSION_TYPE = os.getenv("SESSION_TYPE", "community")
SESSION_ID = os.getenv("SESSION_ID", "")
SESSION_EXPIRY = os.getenv("SESSION_EXPIRY", "")
SESSION_FUNDED_AKT = float(os.getenv("SESSION_FUNDED_AKT", "0"))

# Import MODEL_NAME from config
from config import MODEL_NAME

# ===== CACHES =====
_escrow_cache = {"data": None, "timestamp": 0, "ttl": 300}
_lease_price_cache = {"data": None, "timestamp": 0, "ttl": 300}


def get_akt_price_usd() -> Optional[float]:
    """Fetch current AKT price from CoinGecko API"""
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "akash-network", "vs_currencies": "usd"},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("akash-network", {}).get("usd")
    except Exception as e:
        logger.warning(f"Failed to fetch AKT price: {e}")
    return None


def get_escrow_balance() -> Optional[Dict]:
    """
    Query deployment escrow balance from Akash blockchain.
    Returns escrow balance in AKT and calculated time remaining.
    """
    global _escrow_cache

    now = time.time()

    # Return cached data if fresh
    if _escrow_cache["data"] and (now - _escrow_cache["timestamp"]) < _escrow_cache["ttl"]:
        return _escrow_cache["data"]

    try:
        api_url = "https://akash-rest.publicnode.com/akash/escrow/v1beta3/accounts/list"
        params = {"filters.owner": AKASH_WALLET_ADDRESS, "filters.state": "open"}

        response = requests.get(api_url, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            accounts = data.get("accounts", [])

            if accounts:
                total_uakt = 0
                for account in accounts:
                    balance = account.get("balance", {})
                    total_uakt += int(balance.get("amount", 0))

                escrow_akt = total_uakt / 1_000_000

                result_data = {
                    "escrow_balance_akt": round(escrow_akt, 4),
                    "active_deployments": len(accounts),
                    "source": "blockchain",
                }

                _escrow_cache["data"] = result_data
                _escrow_cache["timestamp"] = now
                logger.info(
                    f"Fetched escrow balance: {escrow_akt:.4f} AKT from {len(accounts)} deployment(s)"
                )
                return result_data
        else:
            logger.warning(f"Akash escrow API returned status {response.status_code}")
    except requests.exceptions.Timeout:
        logger.warning("Timeout querying Akash escrow balance")
    except Exception as e:
        logger.warning(f"Failed to query escrow balance: {e}")

    return None


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
    if (
        _lease_price_cache["data"]
        and (now - _lease_price_cache["timestamp"]) < _lease_price_cache["ttl"]
    ):
        return _lease_price_cache["data"]

    try:
        api_url = "https://akash-rest.publicnode.com/akash/market/v1beta5/leases/list"
        params = {"filters.owner": AKASH_WALLET_ADDRESS, "filters.state": "active"}

        response = requests.get(api_url, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            leases = data.get("leases", [])

            if leases:
                latest_lease = max(
                    leases, key=lambda x: int(x.get("lease", {}).get("id", {}).get("dseq", 0))
                )
                lease = latest_lease.get("lease", {})
                price_uakt = float(lease.get("price", {}).get("amount", 0))

                blocks_per_hour = 554
                hourly_akt = (price_uakt / 1_000_000) * blocks_per_hour
                daily_akt = hourly_akt * 24

                result_data = {
                    "price_uakt_per_block": price_uakt,
                    "hourly_cost_akt": round(hourly_akt, 4),
                    "daily_cost_akt": round(daily_akt, 2),
                    "dseq": lease.get("id", {}).get("dseq"),
                    "source": "blockchain",
                }

                _lease_price_cache["data"] = result_data
                _lease_price_cache["timestamp"] = now
                logger.info(f"Fetched actual lease price: {hourly_akt:.4f} AKT/hr")
                return result_data
        else:
            logger.warning(f"Akash REST API returned status {response.status_code}")

    except requests.exceptions.Timeout:
        logger.warning("Timeout querying Akash lease price via REST API")
    except Exception as e:
        logger.warning(f"Failed to query lease price via REST API: {e}")

    return None


def get_akash_deployment_info() -> Dict:
    """
    Get deployment info from environment variables and actual blockchain query.
    Prefers actual lease price from blockchain, falls back to env vars.
    """
    lease_info = get_actual_lease_price()

    if lease_info:
        hourly_cost = lease_info["hourly_cost_akt"]
        daily_cost = lease_info["daily_cost_akt"]
        price_source = "blockchain"
    else:
        hourly_cost = HOURLY_COST_AKT
        daily_cost = DAILY_COST_AKT
        price_source = "env_var"

    info = {
        "tier": DEPLOYMENT_TIER,
        "tier_name": DEPLOYMENT_TIER_NAME,
        "model": MODEL_NAME,
        "hourly_cost_akt": hourly_cost,
        "daily_cost_akt": daily_cost,
        "price_source": price_source,
        "session_type": SESSION_TYPE,
        "wallet": AKASH_WALLET_ADDRESS,
        "status": "online",
    }

    if SESSION_TYPE == "private" and SESSION_EXPIRY:
        try:
            from datetime import datetime

            expiry = datetime.fromisoformat(SESSION_EXPIRY.replace("Z", "+00:00"))
            now_dt = datetime.utcnow().replace(tzinfo=expiry.tzinfo)
            remaining = (expiry - now_dt).total_seconds()

            info["session_id"] = SESSION_ID
            info["funded_akt"] = SESSION_FUNDED_AKT
            info["hours_remaining"] = max(0, remaining / 3600)
            info["minutes_remaining"] = max(0, remaining / 60)
            info["expires_at"] = SESSION_EXPIRY
            info["expired"] = remaining <= 0
        except Exception as e:
            logger.warning(f"Failed to parse session expiry: {e}")
            info["hours_remaining"] = 0
            info["expired"] = True
    else:
        info["hours_remaining"] = None
        info["days_remaining"] = None

    return info
