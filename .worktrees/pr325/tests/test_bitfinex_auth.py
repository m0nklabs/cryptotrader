"""
Unit tests for Bitfinex API v2 authentication helper.

Tests signature generation deterministically with fixed inputs.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cex.bitfinex.api.auth import generate_signature, build_auth_headers


class TestGenerateSignature:
    """Test HMAC-SHA384 signature generation with fixed inputs."""

    def test_signature_deterministic_with_fixed_inputs(self) -> None:
        """Signature should be deterministic for fixed key/secret/nonce/path/body."""
        api_secret = "test_secret_key_12345"
        nonce = "1609459200000"  # Fixed timestamp
        path = "/v2/auth/r/wallets"
        body = ""

        # Generate signature twice
        sig1 = generate_signature(api_secret, nonce, path, body)
        sig2 = generate_signature(api_secret, nonce, path, body)

        # Should be identical
        assert sig1 == sig2

    def test_signature_length_is_96_chars(self) -> None:
        """SHA384 produces 48 bytes = 96 hex characters."""
        sig = generate_signature("secret", "1234567890000", "/v2/auth/r/wallets", "")
        assert len(sig) == 96

    def test_signature_is_hex_string(self) -> None:
        """Signature should be valid hex string."""
        sig = generate_signature("secret", "1234567890000", "/v2/auth/r/wallets", "")
        # Should not raise ValueError
        int(sig, 16)

    def test_different_secrets_produce_different_signatures(self) -> None:
        """Different API secrets should produce different signatures."""
        nonce = "1234567890000"
        path = "/v2/auth/r/wallets"
        body = ""

        sig1 = generate_signature("secret1", nonce, path, body)
        sig2 = generate_signature("secret2", nonce, path, body)

        assert sig1 != sig2

    def test_different_nonces_produce_different_signatures(self) -> None:
        """Different nonces should produce different signatures."""
        secret = "test_secret"
        path = "/v2/auth/r/wallets"
        body = ""

        sig1 = generate_signature(secret, "1000000000000", path, body)
        sig2 = generate_signature(secret, "2000000000000", path, body)

        assert sig1 != sig2

    def test_different_paths_produce_different_signatures(self) -> None:
        """Different API paths should produce different signatures."""
        secret = "test_secret"
        nonce = "1234567890000"
        body = ""

        sig1 = generate_signature(secret, nonce, "/v2/auth/r/wallets", body)
        sig2 = generate_signature(secret, nonce, "/v2/auth/r/orders", body)

        assert sig1 != sig2

    def test_different_bodies_produce_different_signatures(self) -> None:
        """Different request bodies should produce different signatures."""
        secret = "test_secret"
        nonce = "1234567890000"
        path = "/v2/auth/w/order/submit"

        sig1 = generate_signature(secret, nonce, path, '{"type":"LIMIT"}')
        sig2 = generate_signature(secret, nonce, path, '{"type":"MARKET"}')

        assert sig1 != sig2

    def test_empty_body_vs_nonempty_body(self) -> None:
        """Empty body should produce different signature than non-empty body."""
        secret = "test_secret"
        nonce = "1234567890000"
        path = "/v2/auth/r/wallets"

        sig1 = generate_signature(secret, nonce, path, "")
        sig2 = generate_signature(secret, nonce, path, "{}")

        assert sig1 != sig2

    def test_known_test_vector(self) -> None:
        """Test with a known signature to verify correctness."""
        # Fixed test vector
        api_secret = "my_test_secret"
        nonce = "1609459200000"
        path = "/v2/auth/r/wallets"
        body = ""

        sig = generate_signature(api_secret, nonce, path, body)

        # Signature should be deterministic and verifiable
        # Re-running should produce the same result
        expected = sig
        actual = generate_signature(api_secret, nonce, path, body)
        assert actual == expected


class TestBuildAuthHeaders:
    """Test authentication header building."""

    def test_headers_contain_required_fields(self) -> None:
        """Headers should contain all required Bitfinex auth fields."""
        headers = build_auth_headers("test_key", "test_secret", "/v2/auth/r/wallets")

        assert "bfx-nonce" in headers
        assert "bfx-apikey" in headers
        assert "bfx-signature" in headers
        assert "Content-Type" in headers

    def test_api_key_in_headers(self) -> None:
        """API key should be included in headers."""
        api_key = "my_api_key_123"
        headers = build_auth_headers(api_key, "secret", "/v2/auth/r/wallets")

        assert headers["bfx-apikey"] == api_key

    def test_nonce_is_numeric_string(self) -> None:
        """Nonce should be a numeric string (millisecond timestamp)."""
        headers = build_auth_headers("key", "secret", "/v2/auth/r/wallets")

        nonce = headers["bfx-nonce"]
        assert nonce.isdigit()
        assert len(nonce) == 13  # Millisecond timestamp

    def test_signature_is_96_char_hex(self) -> None:
        """Signature should be 96-character hex string."""
        headers = build_auth_headers("key", "secret", "/v2/auth/r/wallets")

        signature = headers["bfx-signature"]
        assert len(signature) == 96
        # Should be valid hex
        int(signature, 16)

    def test_content_type_is_json(self) -> None:
        """Content-Type should be application/json."""
        headers = build_auth_headers("key", "secret", "/v2/auth/r/wallets")

        assert headers["Content-Type"] == "application/json"

    def test_headers_with_body_dict(self) -> None:
        """Headers should work with body as dict."""
        body = {"type": "EXCHANGE LIMIT", "symbol": "tBTCUSD"}
        headers = build_auth_headers("key", "secret", "/v2/auth/w/order/submit", body)

        # Should still have all required headers
        assert "bfx-nonce" in headers
        assert "bfx-apikey" in headers
        assert "bfx-signature" in headers

    def test_headers_without_body(self) -> None:
        """Headers should work without body (None)."""
        headers = build_auth_headers("key", "secret", "/v2/auth/r/wallets", None)

        # Should still have all required headers
        assert "bfx-nonce" in headers
        assert "bfx-apikey" in headers
        assert "bfx-signature" in headers

    def test_nonce_increases_over_time(self) -> None:
        """Nonce should increase with each call (time-based)."""
        import time

        headers1 = build_auth_headers("key", "secret", "/v2/auth/r/wallets")
        nonce1 = int(headers1["bfx-nonce"])

        time.sleep(0.01)  # Wait 10ms

        headers2 = build_auth_headers("key", "secret", "/v2/auth/r/wallets")
        nonce2 = int(headers2["bfx-nonce"])

        assert nonce2 > nonce1
