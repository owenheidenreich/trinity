"""
Trinity Backend - Input Validation
Validation functions for request parameters
"""

import ipaddress
import re
import socket
from urllib.parse import urlparse


def validate_chat_id(chat_id: str) -> bool:
    """Validate chat_id format - alphanumeric, dash, underscore only."""
    if not chat_id or len(chat_id) > 64:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", chat_id))


def validate_principal_id(principal_id: str) -> bool:
    """Validate ICP principal format."""
    if not principal_id or len(principal_id) > 64:
        return False
    # ICP principals are base32-ish with dashes
    return bool(re.match(r"^[a-z0-9-]+$", principal_id.lower()))


def validate_cid(cid: str) -> bool:
    """Validate IPFS CID format - base32/base58 alphanumeric."""
    if not cid or len(cid) > 100:
        return False
    return bool(re.match(r"^[a-zA-Z0-9]+$", cid))


def is_safe_url(url: str) -> tuple[bool, str]:
    """
    SSRF Protection: Validate URL is safe to fetch.

    Blocks:
    - Private/internal IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
    - Localhost and local hostnames
    - Cloud metadata endpoints (169.254.169.254)
    - Non-HTTP(S) schemes
    - CGNAT (100.64.0.0/10) - RFC 6598 shared address space
    - Multicast (224.0.0.0/4)
    - Documentation ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24)

    Returns:
        (is_safe: bool, error_message: str)
    """
    # Additional ranges not covered by Python's ipaddress checks
    BLOCKED_NETWORKS = [
        ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598) - often overlooked!
        ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1 (documentation)
        ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2 (documentation)
        ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3 (documentation)
        ipaddress.ip_network("224.0.0.0/4"),  # Multicast
        ipaddress.ip_network("240.0.0.0/4"),  # Reserved (future use)
        ipaddress.ip_network("198.18.0.0/15"),  # Benchmark testing (RFC 2544)
    ]

    try:
        parsed = urlparse(url)

        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            return False, "Only HTTP and HTTPS URLs are allowed"

        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: no hostname"

        # Block common localhost variations
        localhost_patterns = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "localtest.me",
            "lvh.me",
            "vcap.me",
        ]
        if hostname.lower() in localhost_patterns:
            return False, "Access to localhost is not allowed"

        # Block cloud metadata endpoints
        metadata_hosts = [
            "169.254.169.254",  # AWS/GCP/Azure metadata
            "metadata.google.internal",
            "metadata.goog",
        ]
        if hostname.lower() in metadata_hosts:
            return False, "Access to cloud metadata endpoints is not allowed"

        # Resolve hostname to check for internal IPs
        try:
            ip_addresses = socket.gethostbyname_ex(hostname)[2]
        except socket.gaierror:
            return False, "Could not resolve hostname"

        for ip_str in ip_addresses:
            try:
                ip = ipaddress.ip_address(ip_str)

                # Block private/internal ranges (Python built-in checks)
                if ip.is_private:
                    return False, f"Access to private IP {ip_str} is not allowed"
                if ip.is_loopback:
                    return False, f"Access to loopback IP {ip_str} is not allowed"
                if ip.is_link_local:
                    return False, f"Access to link-local IP {ip_str} is not allowed"
                if ip.is_reserved:
                    return False, f"Access to reserved IP {ip_str} is not allowed"
                if ip.is_multicast:
                    return False, f"Access to multicast IP {ip_str} is not allowed"

                # Block additional dangerous ranges not caught by built-in checks
                for blocked_net in BLOCKED_NETWORKS:
                    if ip in blocked_net:
                        return (
                            False,
                            f"Access to blocked IP range {ip_str} ({blocked_net}) is not allowed",
                        )

            except ValueError:
                continue

        return True, ""

    except Exception as e:
        return False, f"URL validation error: {str(e)}"
