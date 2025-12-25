"""Unit tests for the ingestion status endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked database."""
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test:test@localhost/test"}):
        from api.main import app

        return TestClient(app)


def test_health(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code in (200, 503)  # 503 if DB not available
    data = response.json()
    assert "status" in data or "detail" in data


def test_ingestion_status_success(client):
    """Test successful ingestion status query."""
    # Mock database connection and results
    test_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with patch("api.main._get_stores") as mock_get_stores:
        mock_stores = Mock()
        mock_get_stores.return_value = mock_stores

        # Mock engine and connection
        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_stores._get_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

        # Mock SQLAlchemy text function
        def text_func(sql):
            return Mock(text=sql)

        mock_stores._require_sqlalchemy.return_value = (Mock(), text_func)

        # Mock query results
        schema_result = Mock()
        schema_result.scalar.return_value = True

        stats_result = Mock()
        stats_result.fetchone.return_value = (test_time, 100)

        # Execute returns different results based on query
        def execute_side_effect(query, *args, **kwargs):
            if "information_schema" in str(query):
                return schema_result
            else:
                return stats_result

        mock_conn.execute.side_effect = execute_side_effect

        response = client.get("/ingestion/status?exchange=bitfinex&symbol=BTCUSD&timeframe=1m")

        assert response.status_code == 200
        data = response.json()
        assert data["db_ok"] is True
        assert data["schema_ok"] is True
        assert data["candles_count"] == 100
        assert data["latest_candle_open_time"] == int(test_time.timestamp() * 1000)


def test_ingestion_status_no_data(client):
    """Test ingestion status when no candles exist for the symbol."""
    with patch("api.main._get_stores") as mock_get_stores:
        mock_stores = Mock()
        mock_get_stores.return_value = mock_stores

        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_stores._get_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

        def text_func(sql):
            return Mock(text=sql)

        mock_stores._require_sqlalchemy.return_value = (Mock(), text_func)

        schema_result = Mock()
        schema_result.scalar.return_value = True

        stats_result = Mock()
        stats_result.fetchone.return_value = (None, 0)

        def execute_side_effect(query, *args, **kwargs):
            if "information_schema" in str(query):
                return schema_result
            else:
                return stats_result

        mock_conn.execute.side_effect = execute_side_effect

        response = client.get("/ingestion/status?exchange=bitfinex&symbol=XXXUSD&timeframe=1m")

        assert response.status_code == 200
        data = response.json()
        assert data["db_ok"] is True
        assert data["schema_ok"] is True
        assert data["candles_count"] == 0
        assert data["latest_candle_open_time"] is None


def test_ingestion_status_schema_missing(client):
    """Test ingestion status when candles table doesn't exist."""
    with patch("api.main._get_stores") as mock_get_stores:
        mock_stores = Mock()
        mock_get_stores.return_value = mock_stores

        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_stores._get_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

        def text_func(sql):
            return Mock(text=sql)

        mock_stores._require_sqlalchemy.return_value = (Mock(), text_func)

        schema_result = Mock()
        schema_result.scalar.return_value = False
        mock_conn.execute.return_value = schema_result

        response = client.get("/ingestion/status?exchange=bitfinex&symbol=BTCUSD&timeframe=1m")

        assert response.status_code == 200
        data = response.json()
        assert data["db_ok"] is True
        assert data["schema_ok"] is False
        assert data["candles_count"] is None
        assert data["latest_candle_open_time"] is None


def test_ingestion_status_db_error(client):
    """Test ingestion status when database is unreachable."""
    with patch("api.main._get_stores") as mock_get_stores:
        mock_stores = Mock()
        mock_get_stores.return_value = mock_stores

        mock_engine = Mock()
        mock_stores._get_engine.return_value = mock_engine
        mock_engine.begin.side_effect = Exception("Connection failed")

        def text_func(sql):
            return Mock(text=sql)

        mock_stores._require_sqlalchemy.return_value = (Mock(), text_func)

        response = client.get("/ingestion/status?exchange=bitfinex&symbol=BTCUSD&timeframe=1m")

        assert response.status_code == 200
        data = response.json()
        assert data["db_ok"] is False
        assert data["schema_ok"] is False
        assert data["candles_count"] is None
        assert data["latest_candle_open_time"] is None
        assert "error" in data
        assert data["error"] == "Exception"


def test_ingestion_status_default_exchange(client):
    """Test that exchange defaults to 'bitfinex' when not specified."""
    with patch("api.main._get_stores") as mock_get_stores:
        mock_stores = Mock()
        mock_get_stores.return_value = mock_stores

        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_stores._get_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

        def text_func(sql):
            return Mock(text=sql)

        mock_stores._require_sqlalchemy.return_value = (Mock(), text_func)

        schema_result = Mock()
        schema_result.scalar.return_value = True
        stats_result = Mock()
        stats_result.fetchone.return_value = (None, 0)

        def execute_side_effect(query, *args, **kwargs):
            if "information_schema" in str(query):
                return schema_result
            else:
                return stats_result

        mock_conn.execute.side_effect = execute_side_effect

        response = client.get("/ingestion/status?symbol=BTCUSD&timeframe=1m")

        assert response.status_code == 200
        data = response.json()
        assert data["db_ok"] is True


def test_ingestion_status_missing_required_params(client):
    """Test that missing required parameters return 422."""
    # Missing symbol
    response = client.get("/ingestion/status?timeframe=1m")
    assert response.status_code == 422

    # Missing timeframe
    response = client.get("/ingestion/status?symbol=BTCUSD")
    assert response.status_code == 422

    # Missing both
    response = client.get("/ingestion/status")
    assert response.status_code == 422
