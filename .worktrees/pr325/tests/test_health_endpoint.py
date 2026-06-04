"""Tests for health check endpoint."""

from unittest.mock import patch, MagicMock
from core.health.checker import HealthChecker, HealthStatus


def test_health_status_dataclass():
    """Test HealthStatus dataclass."""
    status = HealthStatus(
        status="ok",
        latency_ms=15.5,
        message="All good",
        details={"count": 100},
    )

    assert status.status == "ok"
    assert status.latency_ms == 15.5
    assert status.message == "All good"
    assert status.details == {"count": 100}


def test_health_checker_no_database():
    """Test health checker when DATABASE_URL is not set."""
    # Patch os.environ before creating HealthChecker
    with patch.dict("os.environ", {}, clear=True):
        checker = HealthChecker(database_url=None)
        result = checker.check_database()

    assert result.status == "error"
    assert "not configured" in result.message


def test_health_checker_database_ok():
    """Test health checker when database is healthy."""
    checker = HealthChecker(database_url="postgresql://test:test@localhost/test")

    # Mock SQLAlchemy engine and connection
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1000

    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_engine.begin.return_value.__exit__.return_value = None

    with patch("core.health.checker.create_engine", return_value=mock_engine):
        result = checker.check_database()

    assert result.status == "ok"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0
    assert "connected" in result.message.lower()


def test_health_checker_database_error():
    """Test health checker when database connection fails."""
    checker = HealthChecker(database_url="postgresql://invalid:invalid@localhost/invalid")

    # Mock connection failure
    with patch("core.health.checker.create_engine", side_effect=Exception("Connection failed")):
        result = checker.check_database()

    assert result.status == "error"
    assert "error" in result.message.lower()


def test_health_checker_check_all():
    """Test checking all components."""
    checker = HealthChecker(database_url="postgresql://test:test@localhost/test")

    # Mock successful database check
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1000
    mock_result.fetchone.return_value = (None, 0)

    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_engine.begin.return_value.__exit__.return_value = None

    with patch("core.health.checker.create_engine", return_value=mock_engine):
        results = checker.check_all()

    assert "database" in results
    assert "ingestion" in results
    assert isinstance(results["database"], HealthStatus)
    assert isinstance(results["ingestion"], HealthStatus)
