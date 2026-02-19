"""
Session Blueprint — /funding/status, /session/*
================================================
Funding transparency, private session management and status.
"""

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from flask import Blueprint, jsonify, request

from config import (
    AKASH_WALLET_ADDRESS,
    ICP_BACKEND_CANISTER,
    ICP_FRONTEND_CANISTER,
    LIGHTHOUSE_GATEWAY,
    GPU_TYPE,
    MAX_SESSION_HOURS,
    MIN_SESSION_HOURS,
    MODEL_NAME,
    logger,
)
from services.akash import (
    DEPLOYMENT_TIER,
    DEPLOYMENT_TIER_NAME,
    SESSION_ID,
    SESSION_TYPE,
    get_akash_deployment_info,
    get_akt_price_usd,
    get_escrow_balance,
)

from routes.shared import _funding_cache, _funding_cache_lock

session_bp = Blueprint("session", __name__)


# ===== ACTIVE SESSIONS HELPER =====

ACTIVE_SESSIONS_FILE = "/data/active_sessions.json"


def load_active_sessions() -> Dict:
    """Load active sessions from file."""
    paths = [
        Path(ACTIVE_SESSIONS_FILE),
        Path(__file__).parent.parent.parent / "data" / "active_sessions.json",
        Path.home() / ".trinity" / "active_sessions.json",
    ]

    for path in paths:
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


# ===== FUNDING =====

@session_bp.route("/funding/status")
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
        if _funding_cache["data"] and (now - _funding_cache["timestamp"]) < _funding_cache["ttl"]:
            return jsonify(_funding_cache["data"])

    # Fetch fresh data
    akt_price = get_akt_price_usd()
    akash_info = get_akash_deployment_info()
    escrow_info = get_escrow_balance()

    # Add escrow balance and calculate hours remaining
    if escrow_info:
        escrow_akt = escrow_info.get("escrow_balance_akt", 0)
        akash_info["escrow_balance_akt"] = escrow_akt
        akash_info["active_deployments"] = escrow_info.get("active_deployments", 0)

        hourly_cost = akash_info.get("hourly_cost_akt", 0.15)
        if hourly_cost > 0 and escrow_akt > 0:
            hours_remaining = escrow_akt / hourly_cost
            akash_info["hours_remaining"] = round(hours_remaining, 1)
            akash_info["days_remaining"] = round(hours_remaining / 24, 1)

    # Calculate USD values if we have AKT price
    if akt_price:
        akash_info["hourly_cost_usd"] = round(akash_info.get("hourly_cost_akt", 0) * akt_price, 4)
        akash_info["daily_cost_usd"] = round(akash_info.get("daily_cost_akt", 0) * akt_price, 2)
        if "escrow_balance_akt" in akash_info:
            akash_info["escrow_balance_usd"] = round(
                akash_info["escrow_balance_akt"] * akt_price, 2
            )

    funding_data = {
        "timestamp": int(now * 1000),
        "akt_price_usd": akt_price,
        "akash": akash_info,
        "icp": {
            "backend_canister": ICP_BACKEND_CANISTER,
            "frontend_canister": ICP_FRONTEND_CANISTER,
            "cycles_info": "Query canister directly for cycle balance",
        },
        "ipfs": {
            "gateway": LIGHTHOUSE_GATEWAY,
            "storage_info": "Lighthouse plan limits vary; check your dashboard usage.",
            "learn_more": "https://docs.ipfs.tech/concepts/what-is-ipfs/",
        },
        "donations": {
            "akt_address": AKASH_WALLET_ADDRESS,
            "akt_memo": "Trinity Community LLM",
            "icp_canister": ICP_BACKEND_CANISTER,
        },
        "private_session": {
            "enabled": True,
            "fee_structure": {
                "hardware_percent": 95,
                "platform_percent": 5,
            },
            "tiers": [
                {
                    "tier": 3,
                    "name": "Professional",
                    "model": "qwen2.5-coder:32b",
                    "hourly_akt": 1.00,
                    "ram_gb": 48,
                },
            ],
            "min_duration_hours": 1,
            "max_duration_hours": 24,
            "payment_address": AKASH_WALLET_ADDRESS,
        },
    }

    # Thread-safe cache update
    with _funding_cache_lock:
        _funding_cache["data"] = funding_data
        _funding_cache["timestamp"] = now

    return jsonify(funding_data)


# ===== SESSION STATUS =====

@session_bp.route("/session/status")
def session_status():
    """Get current session status (private vs community)."""
    akash_info = get_akash_deployment_info()
    akt_price = get_akt_price_usd()

    if akt_price:
        akash_info["hourly_cost_usd"] = round(akash_info.get("hourly_cost_akt", 0) * akt_price, 4)

    return jsonify(
        {
            "session_type": SESSION_TYPE,
            "session_id": SESSION_ID if SESSION_TYPE == "private" else None,
            "tier": DEPLOYMENT_TIER,
            "tier_name": DEPLOYMENT_TIER_NAME,
            "model": MODEL_NAME,
            "gpu_type": GPU_TYPE,
            **akash_info,
            "akt_price_usd": akt_price,
        }
    )


@session_bp.route("/session/request", methods=["POST"])
def session_request():
    """Request a new private session. Returns payment instructions."""
    data = request.get_json() or {}
    tier = data.get("tier", 3)
    hours = data.get("hours", 1)

    # Single-tier for now — only tier 3 (qwen2.5-coder:32b) is supported
    if tier != 3:
        return jsonify({"error": "Only tier 3 is currently available"}), 400

    if hours < MIN_SESSION_HOURS or hours > MAX_SESSION_HOURS:
        return jsonify({"error": f"Hours must be between {MIN_SESSION_HOURS} and {MAX_SESSION_HOURS}"}), 400

    # Single-tier pricing (multi-tier coming later)
    tier_rates = {3: 1.00}
    tier_names = {3: "Professional"}
    tier_models = {3: "qwen2.5-coder:32b"}

    hourly_rate = tier_rates[tier]
    hardware_akt = hourly_rate * hours

    # Add 5% platform fee
    total_akt = hardware_akt / 0.95

    akt_price = get_akt_price_usd() or 0.5
    total_usd = round(total_akt * akt_price, 2)


    session_id = f"sess_{secrets.token_hex(8)}"

    memo = f"trinity:tier:{tier}:{session_id}"

    return jsonify(
        {
            "payment_address": AKASH_WALLET_ADDRESS,
            "payment_memo": memo,
            "required_akt": round(total_akt, 4),
            "required_usd": total_usd,
            "hardware_akt": round(hardware_akt, 4),
            "platform_fee_akt": round(total_akt - hardware_akt, 4),
            "session_id": session_id,
            "tier": tier,
            "tier_name": tier_names[tier],
            "model": tier_models[tier],
            "hours": hours,
            "expires_in": 3600,
            "instructions": [
                f"1. Send {round(total_akt, 4)} AKT to {AKASH_WALLET_ADDRESS}",
                f"2. Include memo: {memo}",
                "3. Wait 1-2 minutes for blockchain confirmation",
                "4. Your private LLM will be deployed automatically",
            ],
        }
    )


@session_bp.route("/session/check/<session_id>")
def session_check(session_id: str):
    """Check the status of a session by ID."""
    sessions = load_active_sessions()

    if session_id not in sessions:
        return jsonify(
            {
                "session_id": session_id,
                "status": "pending",
                "message": "Waiting for payment confirmation...",
            }
        )

    session = sessions[session_id]

    # Check if expired
    try:
        expiry = datetime.fromisoformat(session.get("expires_at", "").replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if now > expiry:
            return jsonify(
                {
                    "session_id": session_id,
                    "status": "expired",
                    "expired_at": session.get("expires_at"),
                    "message": "Session has expired",
                }
            )
    except Exception:
        pass

    # Check if deployment is complete (has endpoint)
    endpoint = session.get("endpoint") or session.get("uri")
    if endpoint:
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"

        return jsonify(
            {
                "session_id": session_id,
                "status": "active",
                "endpoint": endpoint,
                "expires_at": session.get("expires_at"),
                "model": session.get("model"),
                "tier": session.get("tier"),
                "tier_name": session.get("tier_name"),
                "hours": session.get("hours"),
                "dseq": session.get("dseq"),
            }
        )

    # Payment detected but not yet deployed
    return jsonify(
        {
            "session_id": session_id,
            "status": "deploying",
            "message": "Payment confirmed, deploying your private LLM...",
        }
    )
