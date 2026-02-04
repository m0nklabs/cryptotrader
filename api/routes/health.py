"""Health check API endpoint."""

from __future__ import annotations

import asyncio
import time
from fastapi import APIRouter

from core.health import HealthChecker

router = APIRouter(prefix="/system/health", tags=["health"])

# Track API start time
_api_start_time = time.time()


@router.get("")
async def health_check():
    """Get system health status.

    Returns health status for:
    - Database connectivity and latency
    - Ingestion timer status
    - API uptime
    """
    checker = HealthChecker()

    # Run blocking DB checks in thread pool to avoid blocking event loop
    checks = await asyncio.to_thread(checker.check_all)

    # Calculate API uptime
    uptime_seconds = int(time.time() - _api_start_time)

    # Convert HealthStatus dataclasses to dicts
    result = {
        "api": {
            "status": "ok",
            "uptime_seconds": uptime_seconds,
            "message": "API running",
        }
    }

    for component, status in checks.items():
        result[component] = {
            "status": status.status,
            "message": status.message,
        }
        if status.latency_ms is not None:
            result[component]["latency_ms"] = status.latency_ms
        if status.details:
            result[component]["details"] = status.details

    # Overall status is worst of all components
    all_statuses = [result["api"]["status"]] + [v.status for v in checks.values()]
    if "error" in all_statuses:
        overall_status = "error"
    elif "degraded" in all_statuses:
        overall_status = "degraded"
    else:
        overall_status = "ok"

    result["overall"] = {
        "status": overall_status,
    }

    return result
