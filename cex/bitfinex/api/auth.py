"""
Bitfinex API v2 Authentication Helper
======================================

HMAC-SHA384 signature generation for Bitfinex v2 private REST endpoints.

Security:
- Never logs API keys/secrets
- Designed for read-only endpoints (wallets, account info)
- No trading/execution endpoints

Reference:
- https://docs.bitfinex.com/reference/rest-auth-general
"""

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional


def generate_signature(api_secret: str, nonce: str, path: str, body: str = "") -> str:
    """
    Generate HMAC-SHA384 signature for Bitfinex v2 authenticated requests.
    
    Args:
        api_secret: API secret key (must not be logged)
        nonce: Unique nonce (millisecond timestamp as string)
        path: API path (e.g., "/v2/auth/r/wallets")
        body: JSON body as string (default: empty string for GET requests)
    
    Returns:
        Hex-encoded HMAC-SHA384 signature
        
    Example:
        >>> secret = "test_secret"
        >>> nonce = "1234567890000"
        >>> path = "/v2/auth/r/wallets"
        >>> body = ""
        >>> sig = generate_signature(secret, nonce, path, body)
        >>> isinstance(sig, str)
        True
        >>> len(sig) == 96  # SHA384 produces 48 bytes = 96 hex chars
        True
    """
    # Signature payload format for Bitfinex v2:
    # /api/v2/auth{path}{nonce}{body}
    signature_payload = f"/api{path}{nonce}{body}"
    
    # Create HMAC-SHA384 signature
    h = hmac.new(
        api_secret.encode('utf-8'),
        signature_payload.encode('utf-8'),
        hashlib.sha384
    )
    
    return h.hexdigest()


def build_auth_headers(api_key: str, api_secret: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    Build authentication headers for Bitfinex v2 private REST API request.
    
    Args:
        api_key: API key (must not be logged)
        api_secret: API secret (must not be logged)
        path: API path (e.g., "/v2/auth/r/wallets")
        body: Optional request body as dict (will be JSON-encoded)
    
    Returns:
        Dict with required headers: bfx-nonce, bfx-apikey, bfx-signature, Content-Type
        
    Example:
        >>> headers = build_auth_headers("test_key", "test_secret", "/v2/auth/r/wallets")
        >>> "bfx-nonce" in headers
        True
        >>> "bfx-apikey" in headers
        True
        >>> "bfx-signature" in headers
        True
        >>> headers["bfx-apikey"]
        'test_key'
    """
    # Generate nonce (millisecond timestamp)
    nonce = str(int(time.time() * 1000))
    
    # Serialize body to JSON if provided
    body_str = ""
    if body is not None:
        body_str = json.dumps(body)
    
    # Generate signature
    signature = generate_signature(api_secret, nonce, path, body_str)
    
    # Build headers
    headers = {
        "bfx-nonce": nonce,
        "bfx-apikey": api_key,
        "bfx-signature": signature,
        "Content-Type": "application/json"
    }
    
    return headers
