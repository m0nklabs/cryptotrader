from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.api_server import _json_response
from http.server import BaseHTTPRequestHandler
from io import BytesIO


def test_json_response_creates_valid_json():
    """Test that _json_response generates valid JSON."""
    # Create a minimal mock handler
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    
    payload = {"status": "ok", "count": 42}
    
    _json_response(handler, status=200, payload=payload)
    
    # Verify send_response was called
    handler.send_response.assert_called_once_with(200)
    
    # Verify headers were set
    assert handler.send_header.called
    header_calls = handler.send_header.call_args_list
    header_names = [call[0][0] for call in header_calls]
    
    assert "Content-Type" in header_names
    assert "Cache-Control" in header_names
    assert "Content-Length" in header_names
    
    # Verify JSON was written correctly
    written_data = handler.wfile.getvalue()
    parsed = json.loads(written_data)
    assert parsed == payload


def test_json_response_sets_no_cache():
    """Test that _json_response sets Cache-Control to no-store."""
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    
    _json_response(handler, status=200, payload={"test": True})
    
    # Find Cache-Control header
    header_calls = handler.send_header.call_args_list
    cache_control_value = None
    for call in header_calls:
        if call[0][0] == "Cache-Control":
            cache_control_value = call[0][1]
            break
    
    assert cache_control_value == "no-store"


def test_json_response_handles_different_status_codes():
    """Test that _json_response handles different HTTP status codes."""
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    
    _json_response(handler, status=404, payload={"error": "not_found"})
    
    handler.send_response.assert_called_once_with(404)
    
    written_data = handler.wfile.getvalue()
    parsed = json.loads(written_data)
    assert parsed == {"error": "not_found"}


def test_json_response_handles_empty_payload():
    """Test that _json_response handles empty payloads."""
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    
    _json_response(handler, status=200, payload={})
    
    written_data = handler.wfile.getvalue()
    parsed = json.loads(written_data)
    assert parsed == {}


def test_json_response_compact_format():
    """Test that _json_response uses compact JSON format (no spaces)."""
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    
    payload = {"key": "value", "num": 123}
    
    _json_response(handler, status=200, payload=payload)
    
    written_data = handler.wfile.getvalue().decode("utf-8")
    
    # Compact format should not have spaces after separators
    assert written_data == '{"key":"value","num":123}'

