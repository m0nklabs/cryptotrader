"""Tests for signal alert functionality."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.signals.detector import AlertManager
from core.types import IndicatorSignal, Opportunity


@pytest.fixture
def temp_log_dir():
    """Create temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_opportunity():
    """Create a sample trading opportunity for testing."""
    return Opportunity(
        symbol="BTCUSD",
        timeframe="1h",
        score=75,
        side="BUY",
        signals=(
            IndicatorSignal(
                code="RSI",
                side="BUY",
                strength=70,
                value="RSI=28.5",
                reason="RSI oversold",
            ),
            IndicatorSignal(
                code="VOLUME_SPIKE",
                side="CONFIRM",
                strength=60,
                value="2.5x avg",
                reason="Volume spike detected",
            ),
        ),
    )


def test_alert_manager_disabled_by_default():
    """Test that AlertManager is disabled by default."""
    manager = AlertManager()
    assert manager.enabled is False


def test_alert_manager_enabled_via_env():
    """Test that AlertManager can be enabled via environment variable."""
    with patch.dict(os.environ, {"SIGNAL_ALERTS_ENABLED": "true"}):
        manager = AlertManager()
        assert manager.enabled is True


def test_alert_manager_enabled_via_constructor():
    """Test that AlertManager can be enabled via constructor."""
    manager = AlertManager(enabled=True)
    assert manager.enabled is True


def test_alert_manager_webhook_url_from_env():
    """Test that webhook URL is read from environment."""
    test_url = "https://discord.com/api/webhooks/test"
    with patch.dict(os.environ, {"SIGNAL_WEBHOOK_URL": test_url}):
        manager = AlertManager()
        assert manager.webhook_url == test_url


def test_alert_disabled_does_nothing(sample_opportunity):
    """Test that disabled AlertManager doesn't log or notify."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir)
        manager = AlertManager(enabled=False, log_dir=log_dir)

        manager.alert(sample_opportunity, exchange="bitfinex")

        # No log file should be created
        assert not (log_dir / "signals.log").exists()


def test_log_to_file(sample_opportunity, temp_log_dir):
    """Test that signals are logged to file with structured format."""
    manager = AlertManager(enabled=True, log_dir=temp_log_dir)

    manager.alert(sample_opportunity, exchange="bitfinex")

    # Check log file exists
    log_file = temp_log_dir / "signals.log"
    assert log_file.exists()

    # Read and parse log entry
    with open(log_file, "r") as f:
        log_line = f.read().strip()

    log_entry = json.loads(log_line)

    # Verify structure
    assert "timestamp" in log_entry
    assert log_entry["exchange"] == "bitfinex"
    assert log_entry["symbol"] == "BTCUSD"
    assert log_entry["timeframe"] == "1h"
    assert log_entry["side"] == "BUY"
    assert log_entry["score"] == 75
    assert log_entry["signals"] == ["RSI:BUY:70", "VOLUME_SPIKE:CONFIRM:60"]

    # Verify timestamp is valid ISO format
    datetime.fromisoformat(log_entry["timestamp"])


def test_log_multiple_signals(sample_opportunity, temp_log_dir):
    """Test that multiple signals are logged correctly."""
    manager = AlertManager(enabled=True, log_dir=temp_log_dir)

    # Log first signal
    manager.alert(sample_opportunity, exchange="bitfinex")

    # Log second signal
    opportunity2 = Opportunity(
        symbol="ETHUSD",
        timeframe="4h",
        score=82,
        side="SELL",
        signals=(
            IndicatorSignal(
                code="RSI",
                side="SELL",
                strength=85,
                value="RSI=75.2",
                reason="RSI overbought",
            ),
        ),
    )
    manager.alert(opportunity2, exchange="bitfinex")

    # Read log file
    log_file = temp_log_dir / "signals.log"
    with open(log_file, "r") as f:
        lines = f.readlines()

    assert len(lines) == 2

    # Parse both entries
    entry1 = json.loads(lines[0])
    entry2 = json.loads(lines[1])

    assert entry1["symbol"] == "BTCUSD"
    assert entry2["symbol"] == "ETHUSD"


def test_desktop_notification_with_plyer(sample_opportunity, temp_log_dir):
    """Test desktop notification using plyer."""
    manager = AlertManager(enabled=True, log_dir=temp_log_dir)

    with patch("core.signals.detector.notification") as mock_notify:
        manager._send_desktop_notification(sample_opportunity, exchange="bitfinex")

        mock_notify.notify.assert_called_once()
        call_kwargs = mock_notify.notify.call_args[1]

        assert "BTCUSD" in call_kwargs["title"]
        assert "BUY" in call_kwargs["message"]
        assert "75" in call_kwargs["message"]


def test_desktop_notification_fallback_to_notify_send(sample_opportunity, temp_log_dir):
    """Test fallback to notify-send when plyer fails."""
    manager = AlertManager(enabled=True, log_dir=temp_log_dir)

    # Patch the optional dependency hook inside the module under test
    with patch("core.signals.detector.notification") as mock_notify:
        mock_notify.notify.side_effect = Exception("plyer not available")

        with patch("subprocess.run") as mock_subprocess:
            manager._send_desktop_notification(sample_opportunity, exchange="bitfinex")

            # Should call notify-send
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0][0]
            assert args[0] == "notify-send"
            assert "BTCUSD" in args[1]


def test_desktop_notification_graceful_failure(sample_opportunity, temp_log_dir):
    """Test that desktop notification failures don't crash."""
    manager = AlertManager(enabled=True, log_dir=temp_log_dir)

    # Mock both plyer and subprocess to fail
    with patch("core.signals.detector.notification") as mock_notify:
        mock_notify.notify.side_effect = Exception("plyer not available")

        with patch("subprocess.run", side_effect=Exception("notify-send not available")):
            # Should not raise exception
            manager._send_desktop_notification(sample_opportunity, exchange="bitfinex")


def test_webhook_notification(sample_opportunity, temp_log_dir):
    """Test webhook notification (Discord/Slack)."""
    webhook_url = "https://discord.com/api/webhooks/test"
    manager = AlertManager(enabled=True, webhook_url=webhook_url, log_dir=temp_log_dir)

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        manager._send_webhook(sample_opportunity, exchange="bitfinex")

        mock_post.assert_called_once()
        call_args = mock_post.call_args

        assert call_args[0][0] == webhook_url
        payload = call_args[1]["json"]

        assert "BUY Signal Detected" in payload["content"]
        assert "BTCUSD" in payload["content"]
        assert "75/100" in payload["content"]


def test_webhook_notification_failure_handled(sample_opportunity, temp_log_dir):
    """Test that webhook failures are handled gracefully."""
    webhook_url = "https://discord.com/api/webhooks/test"
    manager = AlertManager(enabled=True, webhook_url=webhook_url, log_dir=temp_log_dir)

    with patch("requests.post", side_effect=Exception("Network error")):
        # Should not raise exception
        manager._send_webhook(sample_opportunity, exchange="bitfinex")


def test_alert_integration(sample_opportunity, temp_log_dir):
    """Test full alert flow with all notification methods."""
    webhook_url = "https://discord.com/api/webhooks/test"
    manager = AlertManager(enabled=True, webhook_url=webhook_url, log_dir=temp_log_dir)

    with patch("core.signals.detector.notification") as mock_notify:
        with patch("core.signals.detector.requests") as mock_requests_module:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_requests_module.post.return_value = mock_response

            manager.alert(sample_opportunity, exchange="bitfinex")

            # Verify file logging
            log_file = temp_log_dir / "signals.log"
            assert log_file.exists()

            # Verify desktop notification
            mock_notify.notify.assert_called_once()

            # Verify webhook
            mock_requests_module.post.assert_called_once()


def test_no_secrets_in_logs(sample_opportunity, temp_log_dir):
    """Test that no secrets or sensitive data are logged."""
    manager = AlertManager(enabled=True, log_dir=temp_log_dir)

    manager.alert(sample_opportunity, exchange="bitfinex")

    # Read log file
    log_file = temp_log_dir / "signals.log"
    with open(log_file, "r") as f:
        log_content = f.read()

    # Verify no API keys, secrets, or sensitive patterns
    assert "API" not in log_content.upper()
    assert "SECRET" not in log_content.upper()
    assert "KEY" not in log_content.upper()
    assert "PASSWORD" not in log_content.upper()
    assert "TOKEN" not in log_content.upper()
