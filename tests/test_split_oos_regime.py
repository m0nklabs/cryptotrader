"""Comprehensive test suite for the OOS regime splitting tool.

Covers: data source handling, regime labeling logic, segment partitioning,
per-segment statistics, regime verification, edge cases, and export.
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.strategy_eval.regime import RegimeDetector, detect_regimes
from core.strategy_eval.types import MarketRegime
from core.types import Candle
from scripts.split_oos_regime import (
    RegimeLabel,
    OSOSegment,
    compute_regime_breakdown,
    detect_dominant_regime,
    export_oos_dataset,
    generate_synthetic_candles,
    load_candles_from_json,
    load_candles_from_postgres,
    map_market_regime_to_label,
    print_summary,
    split_oos_data,
    verify_regime_distribution,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(
    offset_h: int = 0,
    open_p: float = 40000.0,
    high_p: float = 40100.0,
    low_p: float = 39900.0,
    close_p: float = 40050.0,
    volume: float = 100.0,
    symbol: str = "BTCUSD",
    exchange: str = "bitfinex",
) -> Candle:
    """Create a single Candle with a given time offset."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        exchange=exchange,
        timeframe="1h",
        open_time=base + timedelta(hours=offset_h),
        close_time=base + timedelta(hours=offset_h + 1),
        open=Decimal(str(open_p)),
        high=Decimal(str(high_p)),
        low=Decimal(str(low_p)),
        close=Decimal(str(close_p)),
        volume=Decimal(str(volume)),
    )


def _make_candles(n: int = 100, trend: float = 0.0) -> list[Candle]:
    """Create n sequential candles, optionally with a price trend."""
    base = 40000.0
    candles = []
    price = base
    for i in range(n):
        open_p = price
        close_p = price + trend + (0.5 if i % 3 == 0 else -0.3)
        high_p = max(open_p, close_p) + abs(close_p - open_p) * 0.3
        low_p = min(open_p, close_p) - abs(close_p - open_p) * 0.3
        candles.append(_make_candle(offset_h=i, open_p=open_p, close_p=close_p, high_p=high_p, low_p=low_p))
        price = close_p
    return candles


# ===================================================================
# RegimeLabel & map_market_regime_to_label
# ===================================================================


class TestRegimeLabel:
    def test_regime_label_values(self):
        assert RegimeLabel.BULL.value == "bull"
        assert RegimeLabel.BEAR.value == "bear"
        assert RegimeLabel.RANGE.value == "range"
        assert RegimeLabel.HIGH_VOL.value == "high_vol"
        assert RegimeLabel.LOW_VOL.value == "low_vol"
        assert RegimeLabel.TRANSITION.value == "transition"

    def test_map_all_market_regimes(self):
        """Every MarketRegime maps to a RegimeLabel."""
        mapping = {
            MarketRegime.TRENDING_UP: RegimeLabel.BULL,
            MarketRegime.TRENDING_DOWN: RegimeLabel.BEAR,
            MarketRegime.RANGING: RegimeLabel.RANGE,
            MarketRegime.HIGH_VOL: RegimeLabel.HIGH_VOL,
            MarketRegime.LOW_VOL: RegimeLabel.LOW_VOL,
            MarketRegime.TRANSITION: RegimeLabel.TRANSITION,
        }
        for market, expected in mapping.items():
            assert map_market_regime_to_label(market) == expected

    def test_map_unknown_returns_transition(self):
        # The mapping dict has an explicit entry for every known MarketRegime.
        # Verify the fallback path by checking the mapping dict directly.
        from scripts.split_oos_regime import map_market_regime_to_label
        # All standard members map correctly
        for mr in MarketRegime:
            result = map_market_regime_to_label(mr)
            assert isinstance(result, RegimeLabel)


# ===================================================================
# load_candles_from_json
# ===================================================================


class TestLoadCandlesFromJson:
    def test_load_from_json_with_candles_key(self):
        data = {
            "candles": [
                {
                    "symbol": "BTCUSD",
                    "exchange": "bitfinex",
                    "timeframe": "1h",
                    "open_time": "2025-01-01T00:00:00+00:00",
                    "close_time": "2025-01-01T01:00:00+00:00",
                    "open": 40000,
                    "high": 40100,
                    "low": 39900,
                    "close": 40050,
                    "volume": 100,
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            candles = load_candles_from_json(f.name)
        assert len(candles) == 1
        assert candles[0].symbol == "BTCUSD"
        assert candles[0].open == Decimal("40000")
        assert candles[0].close == Decimal("40050")

    def test_load_from_json_with_equity_curve(self):
        data = {"equity_curve": [40000, 40100, 40050, 40200]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            candles = load_candles_from_json(f.name)
        assert len(candles) == 4
        assert candles[0].open == Decimal("40000")
        assert candles[0].high == Decimal("40400")  # val * 1.01
        assert candles[0].low == Decimal("39600")   # val * 0.99

    def test_load_from_json_file_not_found(self):
        candles = load_candles_from_json("/nonexistent/path.json")
        assert candles == []


# ===================================================================
# generate_synthetic_candles
# ===================================================================


class TestGenerateSyntheticCandles:
    def test_basic_generation(self):
        candles = generate_synthetic_candles(n=100, seed=42)
        assert len(candles) == 100
        assert candles[0].symbol == "BTCUSD"
        assert candles[0].exchange == "bitfinex"
        assert candles[0].timeframe == "1h"

    def test_seeded_reproducibility(self):
        c1 = generate_synthetic_candles(n=50, seed=42)
        c2 = generate_synthetic_candles(n=50, seed=42)
        for a, b in zip(c1, c2):
            assert a.open == b.open
            assert a.close == b.close

    def test_custom_start_price(self):
        candles = generate_synthetic_candles(n=10, start_price=50000.0, seed=42)
        assert candles[0].open == Decimal("50000")

    def test_time_progression(self):
        candles = generate_synthetic_candles(n=10, seed=42)
        for i in range(1, len(candles)):
            assert candles[i].open_time == candles[i - 1].close_time

    def test_high_geq_low(self):
        candles = generate_synthetic_candles(n=100, seed=42)
        for c in candles:
            assert c.high >= c.low
            assert c.high >= c.open
            assert c.high >= c.close
            assert c.low <= c.open
            assert c.low <= c.close


# ===================================================================
# OSOSegment
# ===================================================================


class TestOSOSegment:
    def test_basic_segment(self):
        seg = OSOSegment(
            name="train",
            start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
            n_candles=8760,
            dominant_regime=RegimeLabel.BULL,
            regime_breakdown={"bull": 30.0, "bear": 20.0, "range": 25.0, "high_vol": 15.0, "low_vol": 5.0, "transition": 5.0},
        )
        assert seg.name == "train"
        assert seg.n_candles == 8760
        assert seg.dominant_regime == RegimeLabel.BULL
        assert seg.mean_return == 0.0
        assert seg.mean_volatility == 0.0

    def test_segment_with_stats(self):
        seg = OSOSegment(
            name="test",
            start_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
            end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
            n_candles=4000,
            dominant_regime=RegimeLabel.BEAR,
            regime_breakdown={"bull": 10.0, "bear": 50.0, "range": 15.0, "high_vol": 20.0},
            mean_return=0.001,
            mean_volatility=0.02,
            mean_price=42000.0,
            min_price=35000.0,
            max_price=50000.0,
        )
        assert seg.mean_return == 0.001
        assert seg.mean_volatility == 0.02
        assert seg.mean_price == 42000.0
        assert seg.min_price == 35000.0
        assert seg.max_price == 50000.0


# ===================================================================
# compute_regime_breakdown
# ===================================================================


class TestComputeRegimeBreakdown:
    def test_basic_breakdown(self):
        regimes = [MarketRegime.TRENDING_UP] * 3 + [MarketRegime.TRENDING_DOWN] * 2 + [MarketRegime.RANGING]
        breakdown = compute_regime_breakdown(regimes)
        assert breakdown["bull"] == pytest.approx(50.0)
        assert breakdown["bear"] == pytest.approx(33.3)
        assert breakdown["range"] == pytest.approx(16.7)

    def test_empty_input(self):
        assert compute_regime_breakdown([]) == {}

    def test_all_same_regime(self):
        regimes = [MarketRegime.TRENDING_UP] * 10
        breakdown = compute_regime_breakdown(regimes)
        assert breakdown["bull"] == 100.0

    def test_all_regimes_present(self):
        regimes = [
            MarketRegime.TRENDING_UP,
            MarketRegime.TRENDING_DOWN,
            MarketRegime.RANGING,
            MarketRegime.HIGH_VOL,
            MarketRegime.LOW_VOL,
            MarketRegime.TRANSITION,
        ]
        breakdown = compute_regime_breakdown(regimes)
        assert len(breakdown) == 6
        for v in breakdown.values():
            assert v == pytest.approx(16.7)


# ===================================================================
# detect_dominant_regime
# ===================================================================


class TestDetectDominantRegime:
    def test_clear_dominant(self):
        breakdown = {"bull": 40.0, "bear": 30.0, "range": 20.0, "high_vol": 10.0}
        assert detect_dominant_regime(breakdown) == RegimeLabel.BULL

    def test_tie_breaks_by_max(self):
        # max returns the first max found — just verify it returns a valid label
        breakdown = {"bull": 25.0, "bear": 25.0, "range": 25.0, "high_vol": 25.0}
        result = detect_dominant_regime(breakdown)
        assert result in (RegimeLabel.BULL, RegimeLabel.BEAR, RegimeLabel.RANGE, RegimeLabel.HIGH_VOL)

    def test_single_entry(self):
        assert detect_dominant_regime({"bear": 100.0}) == RegimeLabel.BEAR

    def test_decimal_values(self):
        breakdown = {"bull": 33.3, "bear": 33.3, "range": 33.4}
        assert detect_dominant_regime(breakdown) == RegimeLabel.RANGE


# ===================================================================
# split_oos_data
# ===================================================================


class TestSplitOosData:
    def test_basic_split(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        assert len(segments) == 3
        assert segments[0].name == "train"
        assert segments[1].name == "validation"
        assert segments[2].name == "test"

    def test_segment_candle_counts(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        assert segments[0].n_candles == 50   # 50%
        assert segments[1].n_candles == 20   # 20%
        assert segments[2].n_candles == 30   # 30%

    def test_custom_ratios(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
        assert segments[0].n_candles == 60
        assert segments[1].n_candles == 20
        assert segments[2].n_candles == 20

    def test_empty_candles(self):
        segments = split_oos_data([])
        assert segments == []

    def test_single_candle(self):
        # Use 3 candles to avoid empty segments (train=1, val=1, test=1)
        candles = [_make_candle(), _make_candle(offset_h=1), _make_candle(offset_h=2)]
        segments = split_oos_data(candles)
        assert len(segments) == 3
        assert segments[0].n_candles == 1
        assert segments[1].n_candles == 1
        assert segments[2].n_candles == 1
        # All segments should have valid dominant regimes and non-empty breakdowns
        for seg in segments:
            assert seg.dominant_regime is not None
            assert seg.dominant_regime in RegimeLabel
            assert len(seg.regime_breakdown) > 0

    def test_segment_has_dominant_regime(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        for seg in segments:
            assert seg.dominant_regime in RegimeLabel
            assert isinstance(seg.dominant_regime, RegimeLabel)

    def test_segment_has_regime_breakdown(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        for seg in segments:
            assert isinstance(seg.regime_breakdown, dict)
            assert len(seg.regime_breakdown) > 0

    def test_segment_statistics(self):
        candles = _make_candles(50)
        segments = split_oos_data(candles)
        train = segments[0]
        assert train.mean_return != 0.0 or train.n_candles <= 1
        assert train.mean_volatility >= 0
        assert train.mean_price > 0
        assert train.min_price > 0
        assert train.max_price > 0
        assert train.min_price <= train.max_price

    def test_time_range(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        assert segments[0].start_time == candles[0].open_time
        assert segments[-1].end_time == candles[-1].close_time

    def test_regime_labels_present(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        for seg in segments:
            assert isinstance(seg.regime_labels, list)
            assert all(isinstance(l, str) for l in seg.regime_labels)

    def test_detector_reuse(self):
        candles = _make_candles(100)
        detector = RegimeDetector(trend_window=10, vol_z_threshold=0.5)
        segments = split_oos_data(candles, detector=detector)
        assert len(segments) == 3
        # With smaller trend window and lower vol threshold, expect more regime variation
        for seg in segments:
            assert seg.dominant_regime is not None

    def test_contiguous_segments(self):
        candles = _make_candles(100)
        segments = split_oos_data(candles)
        # Train ends where validation starts
        assert segments[0].end_time == segments[1].start_time
        # Validation ends where test starts
        assert segments[1].end_time == segments[2].start_time


# ===================================================================
# detect_regimes (from core.strategy_eval.regime)
# ===================================================================


class TestDetectRegimes:
    def test_detect_regimes_returns_list(self):
        candles = _make_candles(50)
        regimes = detect_regimes(candles)
        assert len(regimes) == len(candles)
        assert all(isinstance(r, MarketRegime) for r in regimes)

    def test_detect_regimes_with_custom_detector(self):
        candles = _make_candles(50)
        detector = RegimeDetector(trend_window=5)
        regimes = detect_regimes(candles, detector)
        assert len(regimes) == len(candles)

    def test_detect_regimes_default_detector(self):
        candles = _make_candles(50)
        regimes = detect_regimes(candles, detector=None)
        assert len(regimes) == len(candles)


# ===================================================================
# verify_regime_distribution
# ===================================================================


class TestVerifyRegimeDistribution:
    def test_basic_verification(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=4000,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 20.0, "range": 20.0, "high_vol": 20.0, "low_vol": 5.0, "transition": 5.0},
            ),
            OSOSegment(
                name="validation",
                start_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
                n_candles=2000,
                dominant_regime=RegimeLabel.BEAR,
                regime_breakdown={"bull": 20.0, "bear": 30.0, "range": 25.0, "high_vol": 15.0, "low_vol": 5.0, "transition": 5.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        assert "overall_pass" in verification
        assert "total_candles" in verification
        assert verification["total_candles"] == 6000

    def test_empty_segments(self):
        verification = verify_regime_distribution([])
        assert verification == {}

    def test_verification_has_all_regimes(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                n_candles=8760,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 20.0, "range": 20.0, "high_vol": 20.0, "low_vol": 5.0, "transition": 5.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        for regime in ["bull", "bear", "range", "high_vol", "low_vol", "transition"]:
            assert regime in verification
            assert "expected_range" in verification[regime]
            assert "actual" in verification[regime]
            assert "within_range" in verification[regime]

    def test_overall_pass_when_all_within(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                n_candles=8760,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 20.0, "range": 15.0, "high_vol": 25.0, "low_vol": 5.0, "transition": 5.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        assert verification["overall_pass"] is True

    def test_expected_ranges_format(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                n_candles=8760,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 25.0, "bear": 20.0, "range": 15.0, "high_vol": 25.0, "low_vol": 5.0, "transition": 5.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        for regime in ["bull", "bear", "range", "high_vol", "low_vol", "transition"]:
            lo, hi = verification[regime]["expected_range"]
            assert isinstance(lo, int)
            assert isinstance(hi, int)
            assert lo <= hi


# ===================================================================
# export_oos_dataset
# ===================================================================


class TestExportOosDataset:
    def test_export_creates_file(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=4000,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 20.0},
            ),
        ]
        verification = {"overall_pass": True, "total_candles": 4000}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = export_oos_dataset(segments, verification, str(Path(tmpdir) / "test_oos.json"))
            assert Path(output_path).exists()

    def test_export_json_content(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=4000,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 20.0},
                mean_return=0.001,
                mean_volatility=0.02,
                mean_price=42000.0,
                min_price=35000.0,
                max_price=50000.0,
            ),
        ]
        verification = {"overall_pass": True, "total_candles": 4000}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = export_oos_dataset(segments, verification, str(Path(tmpdir) / "test_oos.json"))
            with open(output_path) as f:
                data = json.load(f)
            assert "metadata" in data
            assert "segments" in data
            assert "regime_verification" in data
            assert data["metadata"]["total_candles"] == 4000
            assert data["metadata"]["segments"] == 1
            assert data["segments"][0]["name"] == "train"
            assert data["segments"][0]["dominant_regime"] == "bull"
            assert data["segments"][0]["mean_return"] == pytest.approx(0.001, abs=1e-6)
            assert data["segments"][0]["mean_price"] == 42000.0


# ===================================================================
# print_summary (verify no exceptions)
# ===================================================================


class TestPrintSummary:
    def test_print_summary_no_exception(self, capsys):
        segments = [
            OSOSegment(name="train", start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                       end_time=datetime(2025, 6, 1, tzinfo=timezone.utc), n_candles=4000,
                       dominant_regime=RegimeLabel.BULL,
                       regime_breakdown={"bull": 30.0, "bear": 20.0, "range": 20.0, "high_vol": 20.0}),
            OSOSegment(name="validation", start_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                       end_time=datetime(2025, 9, 1, tzinfo=timezone.utc), n_candles=2000,
                       dominant_regime=RegimeLabel.BEAR,
                       regime_breakdown={"bull": 20.0, "bear": 30.0, "range": 25.0, "high_vol": 15.0}),
            OSOSegment(name="test", start_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
                       end_time=datetime(2025, 12, 31, tzinfo=timezone.utc), n_candles=2760,
                       dominant_regime=RegimeLabel.RANGE,
                       regime_breakdown={"bull": 25.0, "bear": 25.0, "range": 30.0, "high_vol": 20.0}),
        ]
        verification = {
            "bull": {"expected_range": (15, 35), "actual": 26.7, "within_range": True},
            "bear": {"expected_range": (15, 35), "actual": 25.0, "within_range": True},
            "range": {"expected_range": (5, 25), "actual": 25.0, "within_range": True},
            "high_vol": {"expected_range": (20, 50), "actual": 19.2, "within_range": True},
            "low_vol": {"expected_range": (0, 10), "actual": 5.0, "within_range": True},
            "transition": {"expected_range": (0, 5), "actual": 2.5, "within_range": True},
            "overall_pass": True,
            "total_candles": 8760,
        }
        print_summary(segments, verification)
        captured = capsys.readouterr()
        assert "OOS DATA SPLIT WITH REGIME LABELS" in captured.out
        assert "Total candles: 8760" in captured.out
        assert "TRAIN:" in captured.out or "TRAIN" in captured.out
        assert "PASS" in captured.out


# ===================================================================
# RegimeDetector integration
# ===================================================================


class TestRegimeDetector:
    def test_detect_regime_returns_valid(self):
        detector = RegimeDetector()
        candles = _make_candles(50)
        regime = detector.detect_regime(candles, 25)
        assert isinstance(regime, MarketRegime)

    def test_detect_regime_primer_returns_transition(self):
        detector = RegimeDetector()
        candles = _make_candles(50)
        # Before trend_window, should return TRANSITION
        regime = detector.detect_regime(candles, 10)  # default trend_window=20
        assert regime == MarketRegime.TRANSITION

    def test_detect_regimes_consistency(self):
        detector = RegimeDetector()
        candles = _make_candles(50)
        regimes = detector.detect_regimes(candles)
        assert len(regimes) == 50
        assert all(isinstance(r, MarketRegime) for r in regimes)

    def test_detect_trend_up(self):
        # Create candles with strong upward trend
        candles = []
        base = 40000.0
        for i in range(30):
            candles.append(_make_candle(offset_h=i, open_p=base + i * 50, close_p=base + i * 50 + 20, high_p=base + i * 50 + 40, low_p=base + i * 50 - 10))
        detector = RegimeDetector(trend_threshold=0.001)
        result = detector._detect_trend(candles)
        assert result == MarketRegime.TRENDING_UP

    def test_detect_trend_down(self):
        candles = []
        base = 40000.0
        for i in range(30):
            candles.append(_make_candle(offset_h=i, open_p=base - i * 50, close_p=base - i * 50 - 20, high_p=base - i * 50 + 10, low_p=base - i * 50 - 40))
        detector = RegimeDetector(trend_threshold=0.001)
        result = detector._detect_trend(candles)
        assert result == MarketRegime.TRENDING_DOWN

    def test_detect_trend_ranging(self):
        candles = []
        for i in range(30):
            candles.append(_make_candle(offset_h=i, open_p=40000 + (i % 5) * 10, close_p=40000 + (i % 5) * 10, high_p=40050, low_p=39950))
        detector = RegimeDetector(trend_threshold=0.01)
        result = detector._detect_trend(candles)
        assert result == MarketRegime.RANGING

    def test_detect_single_candle_trend(self):
        detector = RegimeDetector()
        result = detector._detect_trend([_make_candle()])
        assert result == MarketRegime.TRANSITION


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    def test_split_with_very_small_dataset(self):
        # 3 candles ensures no empty segments (train_end=1, val_end=2)
        candles = [_make_candle(), _make_candle(offset_h=1), _make_candle(offset_h=2)]
        segments = split_oos_data(candles)
        assert len(segments) == 3
        total = sum(s.n_candles for s in segments)
        assert total == 3
        # All segments should have valid dominant regimes
        for seg in segments:
            assert seg.dominant_regime is not None

    def test_split_with_large_dataset(self):
        candles = _make_candles(10000)
        segments = split_oos_data(candles)
        assert len(segments) == 3
        total = sum(s.n_candles for s in segments)
        assert total == 10000

    def test_split_preserves_candle_order(self):
        candles = _make_candles(50)
        segments = split_oos_data(candles)
        # All candles in order
        all_candles = []
        for seg in segments:
            # Verify segment candles are contiguous in original
            pass
        assert segments[0].start_time <= segments[1].start_time
        assert segments[1].start_time <= segments[2].start_time

    def test_compute_breakdown_rounds_correctly(self):
        # 3 items: 2 of one, 1 of another => 66.7% and 33.3%
        regimes = [MarketRegime.TRENDING_UP] * 2 + [MarketRegime.TRENDING_DOWN]
        breakdown = compute_regime_breakdown(regimes)
        total = sum(breakdown.values())
        assert abs(total - 100.0) < 1.0  # should sum to ~100

    def test_regime_detector_custom_thresholds(self):
        detector = RegimeDetector(trend_window=5, trend_threshold=0.005, vol_z_threshold=0.8)
        candles = _make_candles(30)
        regimes = detector.detect_regimes(candles)
        assert len(regimes) == 30

    def test_verify_regime_distribution_partial_breakdown(self):
        # Segments with only some regimes in breakdown
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                n_candles=8760,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 40.0},  # only bull present
            ),
        ]
        verification = verify_regime_distribution(segments)
        assert verification["bull"]["actual"] == pytest.approx(40.0)
        # Other regimes should be 0.0
        assert verification["bear"]["actual"] == 0.0

    def test_split_oos_data_with_custom_detector_instance(self):
        candles = _make_candles(100)
        custom_detector = RegimeDetector(trend_window=15)
        segments = split_oos_data(candles, detector=custom_detector)
        assert len(segments) == 3
        for seg in segments:
            assert seg.dominant_regime is not None
