"""Tests for alerts API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def mock_db_connection():
    """Mock database connection for all tests."""
    with patch("api.routes.alerts._get_db_connection") as mock_conn:
        # Create a mock connection
        mock_connection = AsyncMock()
        mock_conn.return_value = mock_connection

        # Mock close method
        mock_connection.close = AsyncMock()

        yield mock_connection


def test_create_alert(client, mock_db_connection):
    """Test creating a new alert."""
    # Mock the create_alert CRUD function
    with patch("api.routes.alerts.alerts_crud.create_alert") as mock_create:
        from datetime import datetime
        from core.alerts.models import Alert, AlertCondition

        # Setup mock return value
        mock_alert = Alert(
            id=1,
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1h",
            condition=AlertCondition(
                type="price_above",
                operator="crosses_above",
                value=50000.0,
            ),
            enabled=True,
            created_at=datetime.utcnow(),
            trigger_count=0,
        )
        mock_create.return_value = mock_alert

        # Make request
        response = client.post(
            "/alerts/",
            json={
                "symbol": "BTCUSD",
                "exchange": "bitfinex",
                "timeframe": "1h",
                "condition": {
                    "type": "price_above",
                    "operator": "crosses_above",
                    "value": 50000.0,
                },
                "enabled": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["symbol"] == "BTCUSD"
        assert data["exchange"] == "bitfinex"
        assert data["condition_type"] == "price_above"
        assert data["threshold_value"] == 50000.0
        assert data["enabled"] is True


def test_list_alerts(client, mock_db_connection):
    """Test listing alerts."""
    with patch("api.routes.alerts.alerts_crud.list_alerts") as mock_list:
        from datetime import datetime
        from core.alerts.models import Alert, AlertCondition

        # Setup mock return value
        mock_alerts = [
            Alert(
                id=1,
                symbol="BTCUSD",
                exchange="bitfinex",
                timeframe="1h",
                condition=AlertCondition(
                    type="price_above",
                    operator="above",
                    value=50000.0,
                ),
                enabled=True,
                created_at=datetime.utcnow(),
                trigger_count=0,
            ),
            Alert(
                id=2,
                symbol="ETHUSD",
                exchange="binance",
                timeframe="5m",
                condition=AlertCondition(
                    type="rsi_overbought",
                    operator="above",
                    value=70.0,
                    indicator_params={"period": 14},
                ),
                enabled=False,
                created_at=datetime.utcnow(),
                trigger_count=5,
            ),
        ]
        mock_list.return_value = mock_alerts

        # Make request
        response = client.get("/alerts/")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["alerts"]) == 2
        assert data["alerts"][0]["symbol"] == "BTCUSD"
        assert data["alerts"][1]["symbol"] == "ETHUSD"


def test_list_alerts_with_filters(client, mock_db_connection):
    """Test listing alerts with filters."""
    with patch("api.routes.alerts.alerts_crud.list_alerts") as mock_list:
        mock_list.return_value = []

        # Make request with filters
        response = client.get("/alerts/?symbol=BTCUSD&exchange=bitfinex&enabled_only=true")

        assert response.status_code == 200
        # Verify filter params were passed to CRUD function
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["symbol"] == "BTCUSD"
        assert call_kwargs["exchange"] == "bitfinex"
        assert call_kwargs["enabled_only"] is True


def test_get_alert(client, mock_db_connection):
    """Test getting a specific alert."""
    with patch("api.routes.alerts.alerts_crud.get_alert") as mock_get:
        from datetime import datetime
        from core.alerts.models import Alert, AlertCondition

        mock_alert = Alert(
            id=1,
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1h",
            condition=AlertCondition(
                type="price_above",
                operator="above",
                value=50000.0,
            ),
            enabled=True,
            created_at=datetime.utcnow(),
            trigger_count=0,
        )
        mock_get.return_value = mock_alert

        # Make request
        response = client.get("/alerts/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["symbol"] == "BTCUSD"


def test_get_alert_not_found(client, mock_db_connection):
    """Test getting a non-existent alert."""
    with patch("api.routes.alerts.alerts_crud.get_alert") as mock_get:
        mock_get.return_value = None

        # Make request
        response = client.get("/alerts/999")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


def test_update_alert(client, mock_db_connection):
    """Test updating an alert."""
    with patch("api.routes.alerts.alerts_crud.update_alert") as mock_update:
        from datetime import datetime
        from core.alerts.models import Alert, AlertCondition

        mock_alert = Alert(
            id=1,
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1h",
            condition=AlertCondition(
                type="price_above",
                operator="above",
                value=51000.0,  # Updated value
            ),
            enabled=False,  # Updated to disabled
            created_at=datetime.utcnow(),
            trigger_count=0,
        )
        mock_update.return_value = mock_alert

        # Make request
        response = client.patch(
            "/alerts/1",
            json={
                "enabled": False,
                "threshold_value": 51000.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["threshold_value"] == 51000.0


def test_delete_alert(client, mock_db_connection):
    """Test deleting an alert."""
    with patch("api.routes.alerts.alerts_crud.delete_alert") as mock_delete:
        mock_delete.return_value = True

        # Make request
        response = client.delete("/alerts/1")

        assert response.status_code == 204


def test_delete_alert_not_found(client, mock_db_connection):
    """Test deleting a non-existent alert."""
    with patch("api.routes.alerts.alerts_crud.delete_alert") as mock_delete:
        mock_delete.return_value = False

        # Make request
        response = client.delete("/alerts/999")

        assert response.status_code == 404


def test_get_alert_history(client, mock_db_connection):
    """Test getting alert history."""
    with patch("api.routes.alerts.alerts_crud.get_alert_history") as mock_history:
        from datetime import datetime
        from core.alerts.models import AlertHistory

        mock_history_entries = [
            AlertHistory(
                id=1,
                alert_id=1,
                triggered_at=datetime.utcnow(),
                trigger_value=51000.0,
                price=51000.0,
                message="Price crossed above 50000.0",
            ),
            AlertHistory(
                id=2,
                alert_id=1,
                triggered_at=datetime.utcnow(),
                trigger_value=52000.0,
                price=52000.0,
                message="Price crossed above 50000.0",
            ),
        ]
        mock_history.return_value = mock_history_entries

        # Make request
        response = client.get("/alerts/1/history?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["history"]) == 2
        assert data["history"][0]["alert_id"] == 1


def test_get_all_alert_history(client, mock_db_connection):
    """Test getting all alert history."""
    with patch("api.routes.alerts.alerts_crud.get_alert_history") as mock_history:
        from datetime import datetime
        from core.alerts.models import AlertHistory

        mock_history_entries = [
            AlertHistory(
                id=1,
                alert_id=1,
                triggered_at=datetime.utcnow(),
                trigger_value=51000.0,
                price=51000.0,
                message="Alert 1 triggered",
            ),
            AlertHistory(
                id=2,
                alert_id=2,
                triggered_at=datetime.utcnow(),
                trigger_value=70.5,
                price=3500.0,
                message="Alert 2 triggered",
            ),
        ]
        mock_history.return_value = mock_history_entries

        # Make request
        response = client.get("/alerts/history/all?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["history"]) == 2
