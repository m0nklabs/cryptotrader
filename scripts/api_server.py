from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Ensure imports work when invoked as a script (e.g., from systemd).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.storage.postgres.config import PostgresConfig  # noqa: E402
from core.storage.postgres.stores import PostgresStores  # noqa: E402


_MAX_LIMIT = 5000
_SYMBOL_RE = re.compile(r"^[A-Z0-9:]{3,20}$")
_TIMEFRAME_RE = re.compile(r"^[0-9]{1,4}[mhdw]$")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _json_response(handler: BaseHTTPRequestHandler, *, status: int, payload: Any) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _check_db_health(stores: PostgresStores) -> dict[str, Any]:
    """Check database connectivity and query latency."""
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    try:
        start = datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        end = datetime.now(timezone.utc)
        latency_ms = (end - start).total_seconds() * 1000

        return {
            "status": "ok",
            "latency_ms": round(latency_ms, 2),
            "timestamp": int(end.timestamp() * 1000),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": type(exc).__name__,
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        }


def _get_ingestion_stats(stores: PostgresStores) -> dict[str, Any]:
    """Get ingestion timer stats from market_data_job_runs table."""
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    try:
        stmt = text(
            """
            SELECT
                job_type,
                MAX(started_at) AS last_run,
                SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END) AS successful_runs,
                SUM(CASE WHEN error_message IS NOT NULL THEN 1 ELSE 0 END) AS failed_runs
            FROM market_data_job_runs
            GROUP BY job_type
            ORDER BY job_type
            """
        )
        with engine.begin() as conn:
            rows = conn.execute(stmt).fetchall()

        jobs = []
        for job_type, last_run, successful, failed in rows:
            last_run_ms: int | None = None
            if last_run:
                dt = _as_utc(last_run)
                last_run_ms = int(dt.timestamp() * 1000)

            jobs.append(
                {
                    "job_type": str(job_type),
                    "last_run": last_run_ms,
                    "successful_runs": int(successful or 0),
                    "failed_runs": int(failed or 0),
                }
            )

        return {"status": "ok", "jobs": jobs}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}


def _check_systemd_timers() -> dict[str, Any]:
    """Check if systemd timers are active (user-level)."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-timers", "--no-pager", "--output=json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"status": "unavailable", "reason": "systemctl_failed"}

        timers_data = json.loads(result.stdout)
        # Filter for cryptotrader timers
        cryptotrader_timers = [
            t for t in timers_data
            if isinstance(t, dict) and "unit" in t and "cryptotrader" in str(t.get("unit", "")).lower()
        ]

        return {
            "status": "ok",
            "active_timers": len(cryptotrader_timers),
            "timers": [
                {
                    "unit": t.get("unit", ""),
                    "next": t.get("next", ""),
                }
                for t in cryptotrader_timers[:5]  # Limit to 5 timers
            ],
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        # systemd might not be available in all environments (e.g., Docker, CI)
        return {"status": "unavailable", "reason": "systemd_not_available"}


class _Server(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], stores: PostgresStores):
        super().__init__(server_address, _Handler)
        self.stores = stores


class _Handler(BaseHTTPRequestHandler):
    server: _Server  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Keep output minimal; never print DATABASE_URL.
        super().log_message(format, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            return _json_response(self, status=200, payload={"ok": True})

        if parsed.path == "/api/system/status":
            try:
                db_health = _check_db_health(stores=self.server.stores)
                ingestion_stats = _get_ingestion_stats(stores=self.server.stores)
                systemd_timers = _check_systemd_timers()

                # Overall backend status is OK if DB is OK
                backend_status = "ok" if db_health["status"] == "ok" else "error"

                return _json_response(
                    self,
                    status=200,
                    payload={
                        "backend": {
                            "status": backend_status,
                            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        },
                        "database": db_health,
                        "ingestion": ingestion_stats,
                        "systemd_timers": systemd_timers,
                    },
                )
            except Exception as exc:  # pragma: no cover
                return _json_response(
                    self,
                    status=500,
                    payload={
                        "error": "system_status_check_failed",
                        "detail": type(exc).__name__,
                    },
                )

        if parsed.path == "/api/candles/available":
            qs = parse_qs(parsed.query)
            exchange = (qs.get("exchange") or ["bitfinex"])[0].strip()
            try:
                rows = _fetch_available_pairs(stores=self.server.stores, exchange=exchange)
            except Exception as exc:  # pragma: no cover
                return _json_response(self, status=500, payload={"error": "db_error", "detail": type(exc).__name__})

            return _json_response(
                self,
                status=200,
                payload={
                    "exchange": exchange,
                    "pairs": rows,
                },
            )

        if parsed.path != "/api/candles":
            return _json_response(self, status=404, payload={"error": "not_found"})

        qs = parse_qs(parsed.query)
        exchange = (qs.get("exchange") or ["bitfinex"])[0].strip()
        symbol = (qs.get("symbol") or [""])[0].strip().upper()
        timeframe = (qs.get("timeframe") or [""])[0].strip()
        limit_raw = (qs.get("limit") or ["480"])[0].strip()

        if not symbol or not _SYMBOL_RE.match(symbol):
            return _json_response(self, status=400, payload={"error": "invalid_symbol"})
        if not timeframe or not _TIMEFRAME_RE.match(timeframe):
            return _json_response(self, status=400, payload={"error": "invalid_timeframe"})

        try:
            limit = int(limit_raw)
        except ValueError:
            return _json_response(self, status=400, payload={"error": "invalid_limit"})

        if limit < 1:
            return _json_response(self, status=400, payload={"error": "invalid_limit"})
        limit = min(limit, _MAX_LIMIT)

        try:
            candles = _fetch_latest_candles(
                stores=self.server.stores,
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception as exc:  # pragma: no cover
            return _json_response(self, status=500, payload={"error": "db_error", "detail": type(exc).__name__})

        return _json_response(
            self,
            status=200,
            payload={
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": candles,
            },
        )


def _fetch_latest_candles(*, stores: PostgresStores, exchange: str, symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    stmt = text(
        """
                SELECT open_time, open, high, low, close, volume
        FROM candles
        WHERE exchange = :exchange
          AND symbol = :symbol
          AND timeframe = :timeframe
        ORDER BY open_time DESC
        LIMIT :limit
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(
            stmt,
            {"exchange": exchange, "symbol": symbol, "timeframe": timeframe, "limit": int(limit)},
        ).fetchall()

    # Return ascending time for charting.
    rows = list(reversed(rows))

    out: list[dict[str, Any]] = []
    for open_time, open_, high, low, close, volume in rows:
        dt = _as_utc(open_time)
        out.append(
            {
                "t": int(dt.timestamp() * 1000),
                "o": float(open_),
                "h": float(high),
                "l": float(low),
                "c": float(close),
                "v": float(volume),
            }
        )
    return out


def _fetch_available_pairs(*, stores: PostgresStores, exchange: str) -> list[dict[str, Any]]:
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    stmt = text(
        """
        SELECT
            symbol,
            timeframe,
            COUNT(*) AS n,
            MAX(open_time) AS latest_open_time
        FROM candles
        WHERE exchange = :exchange
        GROUP BY symbol, timeframe
        ORDER BY symbol ASC, timeframe ASC
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(stmt, {"exchange": exchange}).fetchall()

    out: list[dict[str, Any]] = []
    for symbol, timeframe, n, latest in rows:
        latest_ms: int | None
        if latest is None:
            latest_ms = None
        else:
            dt = _as_utc(latest)
            latest_ms = int(dt.timestamp() * 1000)
        out.append(
            {
                "symbol": str(symbol),
                "timeframe": str(timeframe),
                "count": int(n),
                "latest_open_time": latest_ms,
            }
        )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Minimal local API for the dashboard (DB-backed).")
    p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787)")
    args = p.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    stores = PostgresStores(config=PostgresConfig(database_url=database_url))
    httpd = _Server((args.host, args.port), stores)
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 0
    finally:
        httpd.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
