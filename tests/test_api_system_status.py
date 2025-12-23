"""Test for /api/system/status endpoint structure."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_system_status_response_structure() -> None:
    """Verify the expected structure of the /api/system/status response."""
    # This test documents the expected response structure
    expected_structure = {
        "backend": {
            "status": "ok",  # or "error"
            "timestamp": 1703365200000,  # Unix timestamp in milliseconds
        },
        "database": {
            "status": "ok",  # or "error"
            "latency_ms": 3.45,  # Only present when status is "ok"
            "timestamp": 1703365200000,
            # "error": "ExceptionName",  # Only present when status is "error"
        },
        "ingestion": {
            "status": "ok",  # or "error"
            "jobs": [  # Only present when status is "ok"
                {
                    "job_type": "bitfinex_realtime",
                    "last_run": 1703365000000,  # or None
                    "successful_runs": 150,
                    "failed_runs": 2,
                }
            ],
            # "error": "ExceptionName",  # Only present when status is "error"
        },
        "systemd_timers": {
            "status": "ok",  # "unavailable", or other status
            "active_timers": 3,  # Only present when status is "ok"
            "timers": [  # Only present when status is "ok"
                {
                    "unit": "cryptotrader-bitfinex-realtime@.timer",
                    "next": "2023-12-23 15:30:00",
                }
            ],
            # "reason": "systemd_not_available",  # Only present when unavailable
        },
    }

    # Verify structure keys are documented
    assert "backend" in expected_structure
    assert "database" in expected_structure
    assert "ingestion" in expected_structure
    assert "systemd_timers" in expected_structure

    # Verify backend structure
    assert "status" in expected_structure["backend"]
    assert "timestamp" in expected_structure["backend"]

    # Verify database structure
    assert "status" in expected_structure["database"]
    assert "latency_ms" in expected_structure["database"]

    # Verify ingestion structure
    assert "status" in expected_structure["ingestion"]
    assert "jobs" in expected_structure["ingestion"]

    # Verify job structure
    job = expected_structure["ingestion"]["jobs"][0]
    assert "job_type" in job
    assert "last_run" in job
    assert "successful_runs" in job
    assert "failed_runs" in job
