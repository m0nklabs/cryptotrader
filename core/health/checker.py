"""Health check logic for system components."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional

from sqlalchemy import create_engine, text
import os

# Module-level engine singleton to avoid creating engines on every request
_engine_cache: dict[str, any] = {}


@dataclass
class HealthStatus:
    """Health status for a component."""

    status: Literal["ok", "degraded", "error"]
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    details: Optional[dict] = None


class HealthChecker:
    """Health checker for system components."""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize health checker.

        Args:
            database_url: Database connection URL. If not provided, reads from DATABASE_URL env var.
        """
        self.database_url = database_url or os.environ.get("DATABASE_URL")

    def _get_engine(self):
        """Get or create a cached database engine."""
        if not self.database_url:
            return None

        if self.database_url not in _engine_cache:
            _engine_cache[self.database_url] = create_engine(self.database_url, echo=False, pool_pre_ping=True)
        return _engine_cache[self.database_url]

    def check_database(self) -> HealthStatus:
        """Check database connectivity and measure latency."""
        if not self.database_url:
            return HealthStatus(
                status="error",
                message="DATABASE_URL not configured",
            )

        try:
            engine = self._get_engine()
            if not engine:
                return HealthStatus(
                    status="error",
                    message="Failed to create database engine",
                )

            # Measure query latency
            start_time = time.time()
            with engine.begin() as conn:
                conn.execute(text("SELECT 1"))
            latency_ms = (time.time() - start_time) * 1000

            # Check if we can query candles table
            with engine.begin() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM candles"))
                candle_count = result.scalar()

            return HealthStatus(
                status="ok",
                latency_ms=round(latency_ms, 2),
                message="Database connected",
                details={"candle_count": candle_count},
            )
        except Exception as exc:
            return HealthStatus(
                status="error",
                message=f"Database error: {type(exc).__name__}",
                details={"error": str(exc)},
            )

    def check_ingestion_timers(self) -> HealthStatus:
        """Check if systemd ingestion timers are active.

        This is a placeholder implementation. In production, you would:
        - Query systemd for timer status
        - Check last run timestamps in market_data_job_runs table
        """
        if not self.database_url:
            return HealthStatus(
                status="degraded",
                message="Cannot check ingestion timers without database",
            )

        try:
            engine = self._get_engine()
            if not engine:
                return HealthStatus(
                    status="degraded",
                    message="Failed to create database engine",
                )

            # Check if market_data_job_runs table exists and has recent entries
            with engine.begin() as conn:
                result = conn.execute(
                    text(
                        """
                    SELECT
                        MAX(started_at) as last_run,
                        COUNT(*) as total_runs
                    FROM market_data_job_runs
                    WHERE started_at > NOW() - INTERVAL '24 hours'
                """
                    )
                )
                row = result.fetchone()

            if row and row[1] > 0:
                return HealthStatus(
                    status="ok",
                    message=f"Ingestion active ({row[1]} runs in last 24h)",
                    details={
                        "last_run": str(row[0]) if row[0] else None,
                        "runs_24h": row[1],
                    },
                )
            else:
                return HealthStatus(
                    status="degraded",
                    message="No recent ingestion runs found",
                )
        except Exception as exc:
            # Table might not exist yet, or query failed
            return HealthStatus(
                status="degraded",
                message="Cannot check ingestion status",
                details={"error": str(exc)},
            )

    def check_all(self) -> dict[str, HealthStatus]:
        """Check all system components."""
        return {
            "database": self.check_database(),
            "ingestion": self.check_ingestion_timers(),
        }
