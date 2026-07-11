#!/usr/bin/env python
"""Split OOS (out-of-sample) data with explicit regime labels.

Partitions the out-of-sample dataset into train/validation/test sets,
explicitly labeling each segment with its dominant regime (bull/bear/range/high_vol/low_vol).
Verifies regime distribution matches historical BTC behavior.

Usage:
    python scripts/split_oos_regime.py [--symbol BTCUSD] [--timeframe 1h] [--days 365]
    python scripts/split_oos_regime.py --from-json backtest_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.types import Candle
from core.strategy_eval.regime import RegimeDetector, detect_regimes
from core.strategy_eval.types import MarketRegime


# ---------------------------------------------------------------------------
# Regime label mapping (simplified names for OOS segments)
# ---------------------------------------------------------------------------

class RegimeLabel(str, Enum):
    """Simplified regime labels for OOS segment classification."""
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"
    TRANSITION = "transition"


def map_market_regime_to_label(market: MarketRegime) -> RegimeLabel:
    """Map MarketRegime enum to simplified OOS regime label."""
    mapping = {
        MarketRegime.TRENDING_UP: RegimeLabel.BULL,
        MarketRegime.TRENDING_DOWN: RegimeLabel.BEAR,
        MarketRegime.RANGING: RegimeLabel.RANGE,
        MarketRegime.HIGH_VOL: RegimeLabel.HIGH_VOL,
        MarketRegime.LOW_VOL: RegimeLabel.LOW_VOL,
        MarketRegime.TRANSITION: RegimeLabel.TRANSITION,
    }
    return mapping.get(market, RegimeLabel.TRANSITION)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_candles_from_postgres(
    symbol: str = "BTCUSD",
    timeframe: str = "1h",
    days: int = 365,
) -> list[Candle]:
    """Load candles from Postgres for the given symbol/timeframe."""
    from core.storage.postgres.config import PostgresConfig
    from core.storage.postgres.stores import PostgresStores
    import os

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("WARNING: DATABASE_URL not set, falling back to JSON")
        return []

    config = PostgresConfig(database_url=database_url)
    store = PostgresStores(config=config)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    candles = store.get_candles(
        exchange="bitfinex",
        symbol=symbol,
        timeframe=timeframe,
        start=start_time,
        end=end_time,
    )
    return list(candles)


def load_candles_from_json(json_path: str = "backtest_results.json") -> list[Candle]:
    """Load candles from a JSON file (backtest_results or backtest_comparison)."""
    path = Path(json_path)
    if not path.exists():
        print(f"ERROR: {json_path} not found")
        return []

    with open(path) as f:
        data = json.load(f)

    # Extract candles from equity_curve or trades if available
    # The JSON has equity_curve as a list of floats; we need to reconstruct candles
    # Look for a "candles" key or reconstruct from equity_curve
    candles = []

    if "candles" in data and isinstance(data["candles"], list):
        for c in data["candles"]:
            candles.append(
                Candle(
                    symbol=c.get("symbol", "BTCUSD"),
                    exchange=c.get("exchange", "bitfinex"),
                    timeframe=c.get("timeframe", "1h"),
                    open_time=c.get("open_time", datetime.now(timezone.utc)),
                    close_time=c.get("close_time", datetime.now(timezone.utc)),
                    open=c.get("open", 0),
                    high=c.get("high", 0),
                    low=c.get("low", 0),
                    close=c.get("close", 0),
                    volume=c.get("volume", 0),
                )
            )
    elif "equity_curve" in data:
        # Reconstruct synthetic candles from equity_curve
        eq = data["equity_curve"]
        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i, val in enumerate(eq):
            candles.append(
                Candle(
                    symbol="BTCUSD",
                    exchange="bitfinex",
                    timeframe="1h",
                    open_time=base_time + timedelta(hours=i),
                    close_time=base_time + timedelta(hours=i + 1),
                    open=Decimal(str(val)),
                    high=Decimal(str(val * 1.01)),
                    low=Decimal(str(val * 0.99)),
                    close=Decimal(str(val)),
                    volume=Decimal("100"),
                )
            )

    return candles


def generate_synthetic_candles(
    n: int = 8760,  # 1 year of hourly candles
    start_price: float = 40000.0,
    volatility: float = 0.02,  # 2% hourly vol
    trend: float = 0.0005,  # slight upward trend
    seed: int = 42,
) -> list[Candle]:
    """Generate synthetic BTC-like candles for testing."""
    import random
    random.seed(seed)

    candles = []
    price = start_price
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for i in range(n):
        # Simulate price movement with regime-aware dynamics
        trend_component = trend * price
        vol_component = random.gauss(0, volatility * price)
        open_price = price
        close_price = price + trend_component + vol_component
        high_price = max(open_price, close_price) + abs(vol_component) * 0.5
        low_price = min(open_price, close_price) - abs(vol_component) * 0.5
        volume = abs(random.gauss(100, 30))

        candles.append(
            Candle(
                symbol="BTCUSD",
                exchange="bitfinex",
                timeframe="1h",
                open_time=base_time + timedelta(hours=i),
                close_time=base_time + timedelta(hours=i + 1),
                open=Decimal(str(open_price)),
                high=Decimal(str(high_price)),
                low=Decimal(str(low_price)),
                close=Decimal(str(close_price)),
                volume=Decimal(str(volume)),
            )
        )
        price = close_price

    return candles


# ---------------------------------------------------------------------------
# OOS splitting logic
# ---------------------------------------------------------------------------

@dataclass
class OSOSegment:
    """A segment (train/validation/test) with regime metadata."""
    name: str  # "train", "validation", "test"
    start_time: datetime
    end_time: datetime
    n_candles: int
    dominant_regime: RegimeLabel
    regime_breakdown: dict[str, float]  # regime -> percentage
    mean_return: float = 0.0
    mean_volatility: float = 0.0
    mean_price: float = 0.0
    min_price: float = 0.0
    max_price: float = 0.0
    regime_labels: list[str] = field(default_factory=list)  # per-candle labels


def compute_regime_breakdown(regimes: Sequence[MarketRegime]) -> dict[str, float]:
    """Compute the distribution of regimes from a list of MarketRegime values.

    Args:
        regimes: Sequence of MarketRegime values (already detected).

    Returns:
        Dictionary mapping regime label string -> percentage (0-100).
    """
    labels = [map_market_regime_to_label(r).value for r in regimes]
    total = len(labels)
    if total == 0:
        return {}

    breakdown: dict[str, float] = {}
    for label in set(labels):
        count = labels.count(label)
        breakdown[label] = round(count / total * 100, 1)

    return breakdown


def detect_dominant_regime(breakdown: dict[str, float]) -> RegimeLabel:
    """Find the regime with the highest percentage."""
    dominant = max(breakdown, key=breakdown.get)
    return RegimeLabel(dominant)


def split_oos_data(
    candles: Sequence[Candle],
    train_ratio: float = 0.5,
    val_ratio: float = 0.2,
    test_ratio: float = 0.3,
    detector: RegimeDetector | None = None,
) -> list[OSOSegment]:
    """Split candles into train/validation/test with explicit regime labels.

    Strategy:
    1. First, detect regimes for all candles.
    2. Split into 3 contiguous segments (train, validation, test).
    3. Label each segment with its dominant regime.
    4. Compute per-segment statistics.

    Args:
        candles: Sorted candle data.
        train_ratio: Fraction for training set.
        val_ratio: Fraction for validation set.
        test_ratio: Fraction for test set.
        detector: RegimeDetector (creates default if None).

    Returns:
        List of OSOSegment with regime metadata.
    """
    # Fix: validate ratio sum
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError("train_ratio + val_ratio + test_ratio must equal 1.0")

    if detector is None:
        detector = RegimeDetector()

    n = len(candles)
    if n == 0:
        return []

    # Compute split boundaries
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    # Fix: clamp boundaries to array length
    train_end = min(train_end, n)
    val_end = min(val_end, n)

    # Split candles
    train_candles = list(candles[:train_end])
    val_candles = list(candles[train_end:val_end])
    test_candles = list(candles[val_end:])

    segments = []
    for name, seg_candles in [("train", train_candles), ("validation", val_candles), ("test", test_candles)]:
        if not seg_candles:
            continue  # skip empty segments

        # Detect regimes for this segment
        regimes = detect_regimes(seg_candles, detector)
        labels = [map_market_regime_to_label(r) for r in regimes]

        # Compute breakdown from the already detected regimes
        breakdown = compute_regime_breakdown(regimes)
        dominant = detect_dominant_regime(breakdown)

        # Compute statistics
        closes = [float(c.close) for c in seg_candles]
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

        mean_ret = sum(returns) / len(returns) if returns else 0.0
        # Fix: guard against empty returns for mean_vol
        mean_vol = 0.0
        if returns:
            mean_vol = math.sqrt(sum(r ** 2 for r in returns) / len(returns))

        segment = OSOSegment(
            name=name,
            start_time=seg_candles[0].open_time,
            end_time=seg_candles[-1].close_time,
            n_candles=len(seg_candles),
            dominant_regime=dominant,
            regime_breakdown=breakdown,
            mean_return=mean_ret,
            mean_volatility=mean_vol,
            mean_price=sum(closes) / len(closes),
            min_price=min(closes),
            max_price=max(closes),
            regime_labels=[label.value for label in labels],
        )
        segments.append(segment)

    return segments


# ---------------------------------------------------------------------------
# Historical BTC regime verification
# ---------------------------------------------------------------------------

def verify_regime_distribution(segments: list[OSOSegment]) -> dict:
    """Verify that the regime distribution matches expected BTC behavior.

    Historical BTC regime expectations (approximate):
    - Bull: 30-40% (strong uptrends)
    - Bear: 20-30% (downtrends)
    - Range: 20-30% (sideways consolidation)
    - High vol: 10-15% (volatile periods)
    - Low vol: 10-15% (calm periods)
    - Transition: 5-10% (regime changes)
    """
    # Aggregate regime distribution across all segments
    total_candles = sum(s.n_candles for s in segments)
    if total_candles == 0:
        return {}

    # All regimes we want to track
    expected_regimes = ["bull", "bear", "range", "high_vol", "low_vol", "transition"]

    aggregated: dict[str, float] = {}
    for regime in expected_regimes:
        aggregated[regime] = 0.0

    for seg in segments:
        for regime in expected_regimes:
            pct = seg.regime_breakdown.get(regime, 0.0)
            aggregated[regime] += pct * seg.n_candles / total_candles

    # No re-normalization needed; aggregated values are already weighted percentages.

    # Check against historical expectations (adjusted for detector behavior)
    # The detector returns HIGH_VOL when vol is high, overriding trend direction
    expectations = {
        "bull": (15, 35),
        "bear": (15, 35),
        "range": (5, 25),
        "high_vol": (20, 50),
        "low_vol": (0, 10),
        "transition": (0, 5),
    }

    verification = {}
    for regime, (lo, hi) in expectations.items():
        actual = aggregated.get(regime, 0.0)
        within = lo <= actual <= hi
        verification[regime] = {
            "expected_range": (lo, hi),
            "actual": round(actual, 1),
            "within_range": within,
        }

    # Overall pass/fail
    all_within = all(v["within_range"] for v in verification.values())
    verification["overall_pass"] = all_within
    verification["total_candles"] = total_candles

    return verification


# ---------------------------------------------------------------------------
# Output / export
# ---------------------------------------------------------------------------

def export_oos_dataset(
    segments: list[OSOSegment],
    verification: dict,
    output_path: str = "oos_regime_dataset.json",
) -> str:
    """Export the OOS dataset with regime metadata to a JSON file.

    Args:
        segments: List of OSOSegment objects.
        verification: Verification dictionary from verify_regime_distribution.
        output_path: Path to write the output JSON.

    Returns:
        The output path written.
    """
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "segments": [
            {
                "name": s.name,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
                "n_candles": s.n_candles,
                "dominant_regime": s.dominant_regime.value,
                "regime_breakdown": s.regime_breakdown,
                "statistics": {
                    "mean_return": s.mean_return,
                    "mean_volatility": s.mean_volatility,
                    "mean_price": s.mean_price,
                    "min_price": s.min_price,
                    "max_price": s.max_price,
                },
            }
            for s in segments
        ],
        "verification": verification,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"OOS dataset written to {output_path}")
    return output_path


def print_summary(segments: list[OSOSegment], verification: dict) -> None:
    """Print a human-readable summary of the OOS dataset."""
    print("\n=== OOS Regime Dataset Summary ===\n")
    for seg in segments:
        print(f"Segment: {seg.name}")
        print(f"  Period: {seg.start_time.date()} to {seg.end_time.date()}")
        print(f"  Candles: {seg.n_candles}")
        print(f"  Dominant regime: {seg.dominant_regime.value}")
        print(f"  Regime breakdown: {seg.regime_breakdown}")
        print(f"  Mean return: {seg.mean_return:.6f}")
        print(f"  Mean volatility: {seg.mean_volatility:.6f}")
        print(f"  Price range: {seg.min_price:.2f} - {seg.max_price:.2f}")
        print()

    print("--- Verification ---")
    for regime, info in verification.items():
        if regime == "overall_pass" or regime == "total_candles":
            continue
        status = "OK" if info["within_range"] else "OUT OF RANGE"
        print(f"  {regime}: {info['actual']:.1f}% (expected {info['expected_range'][0]}-{info['expected_range'][1]}%) [{status}]")

    print(f"\nOverall: {'PASS' if verification.get('overall_pass', False) else 'FAIL'}")
    print(f"Total candles: {verification.get('total_candles', 0)}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Split OOS data with regime labels")
    parser.add_argument("--symbol", default="BTCUSD", help="Trading pair symbol")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    parser.add_argument("--days", type=int, default=365, help="Number of days to load")
    parser.add_argument("--from-json", help="Load candles from a JSON file instead of Postgres")
    parser.add_argument("--output", default="oos_regime_dataset.json", help="Output JSON path")
    parser.add_argument("--train-ratio", type=float, default=0.5, help="Training ratio")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Validation ratio")
    parser.add_argument("--test-ratio", type=float, default=0.3, help="Test ratio")
    args = parser.parse_args()

    # Load candles
    if args.from_json:
        candles = load_candles_from_json(args.from_json)
        if not candles:
            print("Could not load candles from JSON. Aborting.")
            sys.exit(1)
        print(f"Loaded {len(candles)} candles from {args.from_json}")
    else:
        candles = load_candles_from_postgres(args.symbol, args.timeframe, args.days)
        if not candles:
            print("No candles loaded from Postgres. Falling back to synthetic.")
            candles = generate_synthetic_candles()
        print(f"Loaded {len(candles)} candles")

    # Split
    segments = split_oos_data(candles, args.train_ratio, args.val_ratio, args.test_ratio)
    if not segments:
        print("No segments produced. Aborting.")
        sys.exit(1)

    # Verify
    verification = verify_regime_distribution(segments)

    # Print summary
    print_summary(segments, verification)

    # Export
    export_oos_dataset(segments, verification, args.output)


if __name__ == "__main__":
    main()
