from __future__ import annotations

import argparse
import json
import os
import re
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
_GAP_STATS_WINDOW_HOURS = 24


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

        if parsed.path == "/api/market-cap":
            try:
                ranks = _fetch_market_cap_ranks(stores=self.server.stores)
                age = _fetch_market_cap_data_age(stores=self.server.stores)
            except Exception as exc:  # pragma: no cover
                return _json_response(self, status=500, payload={"error": "db_error", "detail": type(exc).__name__})
            
            return _json_response(
                self,
                status=200,
                payload={
                    "ranks": ranks,
                    "age_seconds": age,
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

        if parsed.path == "/api/gaps/summary":
            try:
                summary = _fetch_gap_summary(stores=self.server.stores)
            except Exception as exc:  # pragma: no cover
                return _json_response(self, status=500, payload={"error": "db_error", "detail": type(exc).__name__})

            return _json_response(self, status=200, payload=summary)

        if parsed.path == "/api/signals":
            qs = parse_qs(parsed.query)
            exchange = (qs.get("exchange") or ["bitfinex"])[0].strip()
            symbol = (qs.get("symbol") or [""])[0].strip().upper() if qs.get("symbol") else None
            timeframe = (qs.get("timeframe") or [""])[0].strip() if qs.get("timeframe") else None
            limit_raw = (qs.get("limit") or ["20"])[0].strip()

            try:
                limit = int(limit_raw)
            except ValueError:
                return _json_response(self, status=400, payload={"error": "invalid_limit"})

            limit = max(1, min(limit, 100))

            try:
                signals = _fetch_signals(
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
                    "signals": signals,
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


def _fetch_gap_summary(*, stores: PostgresStores) -> dict[str, Any]:
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    stmt = text(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE repaired_at IS NULL) AS open_gaps,
            COUNT(*) FILTER (WHERE repaired_at >= NOW() - INTERVAL '{_GAP_STATS_WINDOW_HOURS} hours') AS repaired_24h,
            MIN(expected_open_time) FILTER (WHERE repaired_at IS NULL) AS oldest_open_gap
        FROM candle_gaps
        """
    )

    with engine.begin() as conn:
        row = conn.execute(stmt).fetchone()

    if row is None:
        return {
            "open_gaps": 0,
            "repaired_24h": 0,
            "oldest_open_gap": None,
        }

    open_gaps, repaired_24h, oldest_gap = row
    oldest_gap_ms: int | None = None
    if oldest_gap is not None:
        dt = _as_utc(oldest_gap)
        oldest_gap_ms = int(dt.timestamp() * 1000)

    return {
        "open_gaps": int(open_gaps),
        "repaired_24h": int(repaired_24h),
        "oldest_open_gap": oldest_gap_ms,
    }


def _fetch_signals(
    *,
    stores: PostgresStores,
    exchange: str,
    symbol: str | None,
    timeframe: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch latest signals/opportunities from the database."""
    opportunities = stores.get_opportunities(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )

    out: list[dict[str, Any]] = []
    for opp in opportunities:
        created_ms: int | None = None
        if opp.created_at is not None:
            dt = _as_utc(opp.created_at)
            created_ms = int(dt.timestamp() * 1000)

        signals_list = [
            {
                "code": sig.code,
                "side": sig.side,
                "strength": sig.strength,
                "value": sig.value,
                "reason": sig.reason,
            }
            for sig in opp.signals
        ]

        out.append(
            {
                "symbol": opp.symbol,
                "timeframe": opp.timeframe,
                "score": opp.score,
                "side": opp.side,
                "signals": signals_list,
                "created_at": created_ms,
            }
        )

    return out
        dt = _as_utc(oldest_gap)
        oldest_gap_ms = int(dt.timestamp() * 1000)

    return {
        "open_gaps": int(open_gaps),
        "repaired_24h": int(repaired_24h),
        "oldest_open_gap": oldest_gap_ms,
    }


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
