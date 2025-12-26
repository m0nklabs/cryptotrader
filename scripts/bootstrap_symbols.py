#!/usr/bin/env python3
"""Bootstrap market-data ingestion for a set of symbols.

What it does:
- Runs an initial backfill for each (symbol,timeframe) for a recent lookback window.
- Creates instance env files under ~/.config/cryptotrader/ for systemd template units.
- Links template units into ~/.config/systemd/user/ (if not already linked).
- Enables the realtime timer (1m cadence) and the gap-repair timer for each instance.

This is intended for local/server operation and does not print secrets.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


_REPO_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_SYMBOLS = [
    # Curated "top" USD pairs for Bitfinex (adjust via --symbols).
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "ADAUSD",
    "DOGEUSD",
    "LTCUSD",
    "AVAXUSD",
    "LINKUSD",
    "DOTUSD",
]


@dataclass(frozen=True)
class Instance:
    symbol: str
    timeframe: str

    @property
    def instance_name(self) -> str:
        return f"{self.symbol}-{self.timeframe}"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        # Keep literal value; do not attempt shell expansion.
        data[k] = v
    return data


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=str(_REPO_ROOT), env=env, check=True)


def _link_user_unit(template_path: Path) -> None:
    """Link a unit file into ~/.config/systemd/user via symlink.

    We avoid `systemctl --user link` to keep behavior predictable across distros.
    """

    user_dir = Path.home() / ".config" / "systemd" / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    link_path = user_dir / template_path.name
    if link_path.exists() or link_path.is_symlink():
        return
    link_path.symlink_to(template_path)


def _write_instance_env(path: Path, *, symbol: str, timeframe: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"CT_SYMBOL={symbol}\nCT_TIMEFRAME={timeframe}\n"
    path.write_text(content, encoding="utf-8")


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _instances(symbols: Iterable[str], timeframe: str) -> list[Instance]:
    out: list[Instance] = []
    for sym in symbols:
        s = sym.strip()
        if s:
            out.append(Instance(symbol=s, timeframe=timeframe))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap symbols: initial backfill + enable systemd timers")
    parser.add_argument(
        "--exchange",
        default="bitfinex",
        choices=["bitfinex", "binance"],
        help="Exchange to use (default: bitfinex)",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols (default: curated top USD pairs)",
    )
    parser.add_argument("--timeframe", default="1m", help="Timeframe to backfill/enable (default: 1m)")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=3,
        help="Initial backfill window size (days). Default: 3",
    )
    parser.add_argument(
        "--enable-gap-repair",
        action="store_true",
        help="Also enable the gap-repair timer for each instance",
    )
    parser.add_argument(
        "--no-enable-timers",
        action="store_true",
        help="Only create env files + run initial backfill; do not enable timers",
    )
    parser.add_argument(
        "--ignore-errors",
        action="store_true",
        help="Continue even if some symbols fail backfill",
    )

    args = parser.parse_args(argv)

    exchange = str(args.exchange)
    symbols = [s for s in (args.symbols.split(",") if args.symbols else []) if s.strip()]
    tf = str(args.timeframe)

    # Load repo-local env if present (DATABASE_URL typically lives here).
    env = os.environ.copy()
    env.update(_parse_env_file(_REPO_ROOT / ".env"))
    env.update(_parse_env_file(_REPO_ROOT / ".secrets" / ".env"))

    if not env.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set (set it in environment or /home/flip/cryptotrader/.env)")

    # Link template units (safe if already present).
    _link_user_unit(_REPO_ROOT / "systemd" / f"cryptotrader-{exchange}-backfill@.service")
    _link_user_unit(_REPO_ROOT / "systemd" / f"cryptotrader-{exchange}-realtime@.timer")
    if args.enable_gap_repair:
        _link_user_unit(_REPO_ROOT / "systemd" / f"cryptotrader-{exchange}-gap-repair@.service")
        _link_user_unit(_REPO_ROOT / "systemd" / f"cryptotrader-{exchange}-gap-repair@.timer")

    _run(["systemctl", "--user", "daemon-reload"], env=env)

    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=int(args.lookback_days))

    failures: list[str] = []

    for inst in _instances(symbols, tf):
        instance_name = inst.instance_name

        backfill_env_path = Path.home() / ".config" / "cryptotrader" / f"{exchange}-backfill-{instance_name}.env"
        _write_instance_env(backfill_env_path, symbol=inst.symbol, timeframe=inst.timeframe)

        # Select the correct backfill module based on exchange
        backfill_module = f"core.market_data.{exchange}_backfill"

        # Initial backfill: for a brand new symbol, --resume would fail.
        cmd = [
            str(_REPO_ROOT / ".venv" / "bin" / "python"),
            "-m",
            backfill_module,
            "--symbol",
            inst.symbol,
            "--timeframe",
            inst.timeframe,
            "--exchange",
            exchange,
            "--start",
            _iso_utc(start),
            "--end",
            _iso_utc(now),
        ]

        try:
            _run(cmd, env=env)
        except Exception:
            failures.append(inst.symbol)
            if not args.ignore_errors:
                raise
            continue

        if args.enable_gap_repair:
            gap_env_path = Path.home() / ".config" / "cryptotrader" / f"{exchange}-gap-repair-{instance_name}.env"
            _write_instance_env(gap_env_path, symbol=inst.symbol, timeframe=inst.timeframe)

        if args.no_enable_timers:
            continue

        _run(
            ["systemctl", "--user", "enable", "--now", f"cryptotrader-{exchange}-realtime@{instance_name}.timer"], env=env
        )
        if args.enable_gap_repair:
            _run(
                ["systemctl", "--user", "enable", "--now", f"cryptotrader-{exchange}-gap-repair@{instance_name}.timer"],
                env=env,
            )

    if failures:
        raise SystemExit(f"Some symbols failed initial backfill: {', '.join(failures)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
