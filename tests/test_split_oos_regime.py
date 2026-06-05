"""Tests for OOS data splitting with explicit regime labels."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pytest

from scripts.split_oos_regime import (
    RegimeLabel,
    OSOSegment,
    detect_dominant_regime,
    export_oos_dataset,
    generate_synthetic_candles,
    map_market_regime_to_label,
    split_oos_data,
    verify_regime_distribution,
)
from core.strategy_eval.regime import RegimeDetector
from core.strategy_eval.types import MarketRegime
from core.types import Candle


def _make_candle(open_time: datetime, close: float) -> Candle:
    """Helper to create a simple candle."""
    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=open_time,
        close_time=open_time,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=100,
    )


class TestMapMarketRegime:
    """Test mapping from MarketRegime to RegimeLabel."""

    def test_trending_up_maps_to_bull(self):
        assert map_market_regime_to_label(MarketRegime.TRENDING_UP) == RegimeLabel.BULL

    def test_trending_down_maps_to_bear(self):
        assert map_market_regime_to_label(MarketRegime.TRENDING_DOWN) == RegimeLabel.BEAR

    def test_ranging_maps_to_range(self):
        assert map_market_regime_to_label(MarketRegime.RANGING) == RegimeLabel.RANGE

    def test_high_vol_maps_to_high_vol(self):
        assert map_market_regime_to_label(MarketRegime.HIGH_VOL) == RegimeLabel.HIGH_VOL

    def test_low_vol_maps_to_low_vol(self):
        assert map_market_regime_to_label(MarketRegime.LOW_VOL) == RegimeLabel.LOW_VOL

    def test_transition_maps_to_transition(self):
        assert map_market_regime_to_label(MarketRegime.TRANSITION) == RegimeLabel.TRANSITION


class TestDetectDominantRegime:
    """Test dominant regime detection."""

    def test_dominant_regime_returns_highest(self):
        breakdown = {"bull": 30.0, "bear": 20.0, "range": 15.0, "high_vol": 25.0}
        assert detect_dominant_regime(breakdown) == RegimeLabel.BULL

    def test_dominant_regime_handles_ties(self):
        breakdown = {"bull": 25.0, "bear": 25.0, "range": 10.0}
        result = detect_dominant_regime(breakdown)
        assert result in (RegimeLabel.BULL, RegimeLabel.BEAR)


class TestSplitOOSData:
    """Test OOS data splitting."""

    def test_split_produces_three_segments(self):
        candles = generate_synthetic_candles(1000)
        segments = split_oos_data(candles)
        assert len(segments) == 3
        assert [s.name for s in segments] == ["train", "validation", "test"]

    def test_split_respects_ratios(self):
        candles = generate_synthetic_candles(1000)
        segments = split_oos_data(candles, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
        assert segments[0].n_candles == 600  # train
        assert segments[1].n_candles == 200  # validation
        assert segments[2].n_candles == 200  # test

    def test_split_with_empty_candles(self):
        segments = split_oos_data([])
        assert segments == []

    def test_split_labels_each_segment(self):
        candles = generate_synthetic_candles(1000)
        segments = split_oos_data(candles)
        for seg in segments:
            assert seg.dominant_regime in RegimeLabel
            assert isinstance(seg.regime_breakdown, dict)
            assert len(seg.regime_breakdown) > 0

    def test_split_computes_statistics(self):
        candles = generate_synthetic_candles(1000)
        segments = split_oos_data(candles)
        for seg in segments:
            assert seg.n_candles > 0
            assert seg.start_time <= seg.end_time
            assert seg.min_price <= seg.max_price
            assert seg.min_price > 0
            assert seg.max_price > 0

    def test_split_custom_detector(self):
        candles = generate_synthetic_candles(1000)
        detector = RegimeDetector(trend_threshold=0.02, vol_z_threshold=1.5)
        segments = split_oos_data(candles, detector=detector)
        assert len(segments) == 3


class TestVerifyRegimeDistribution:
    """Test regime distribution verification."""

    def test_verification_returns_dict(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=500,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 25.0, "range": 20.0, "high_vol": 20.0},
            ),
            OSOSegment(
                name="validation",
                start_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
                n_candles=300,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 35.0, "bear": 20.0, "range": 25.0, "high_vol": 15.0},
            ),
            OSOSegment(
                name="test",
                start_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 12, 1, tzinfo=timezone.utc),
                n_candles=200,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 28.0, "bear": 30.0, "range": 18.0, "high_vol": 22.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        assert isinstance(verification, dict)
        assert "overall_pass" in verification
        assert "total_candles" in verification

    def test_verification_includes_all_regimes(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=500,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 25.0, "range": 20.0, "high_vol": 20.0, "low_vol": 5.0, "transition": 0.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        for regime in ["bull", "bear", "range", "high_vol", "low_vol", "transition"]:
            assert regime in verification
            assert "expected_range" in verification[regime]
            assert "actual" in verification[regime]
            assert "within_range" in verification[regime]

    def test_verification_passes_reasonable_data(self):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=500,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 25.0, "range": 20.0, "high_vol": 20.0},
            ),
            OSOSegment(
                name="validation",
                start_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
                n_candles=300,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 32.0, "bear": 23.0, "range": 22.0, "high_vol": 22.0},
            ),
            OSOSegment(
                name="test",
                start_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 12, 1, tzinfo=timezone.utc),
                n_candles=200,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 28.0, "bear": 27.0, "range": 18.0, "high_vol": 25.0},
            ),
        ]
        verification = verify_regime_distribution(segments)
        assert verification["overall_pass"] is True


class TestExportOOSDataset:
    """Test JSON export of OOS dataset."""

    def test_export_creates_json_file(self, tmp_path):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=500,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 25.0},
                mean_return=0.01,
                mean_volatility=0.02,
                mean_price=40000.0,
                min_price=35000.0,
                max_price=45000.0,
            ),
        ]
        verification = {"bull": {"expected_range": [15, 35], "actual": 30.0, "within_range": True}}
        output_path = str(tmp_path / "test_oos.json")
        export_oos_dataset(segments, verification, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "metadata" in data
        assert "segments" in data
        assert "regime_verification" in data
        assert len(data["segments"]) == 1
        assert data["segments"][0]["name"] == "train"

    def test_export_contains_all_metadata(self, tmp_path):
        segments = [
            OSOSegment(
                name="train",
                start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
                n_candles=500,
                dominant_regime=RegimeLabel.BULL,
                regime_breakdown={"bull": 30.0, "bear": 25.0},
                mean_return=0.01,
                mean_volatility=0.02,
                mean_price=40000.0,
                min_price=35000.0,
                max_price=45000.0,
            ),
        ]
        verification = {"overall_pass": True, "total_candles": 500}
        output_path = str(tmp_path / "test_oos.json")
        export_oos_dataset(segments, verification, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert data["metadata"]["total_candles"] == 500
        assert data["metadata"]["segments"] == 1
        assert data["regime_verification"]["overall_pass"] is True


class TestGenerateSyntheticCandles:
    """Test synthetic candle generation."""

    def test_generate_correct_count(self):
        candles = generate_synthetic_candles(n=100)
        assert len(candles) == 100

    def test_generate_time_sorted(self):
        candles = generate_synthetic_candles(n=100)
        for i in range(1, len(candles)):
            assert candles[i].open_time >= candles[i - 1].open_time

    def test_generate_positive_prices(self):
        candles = generate_synthetic_candles(n=100)
        for c in candles:
            assert c.open > 0
            assert c.high >= c.open
            assert c.low <= c.open
            assert c.close > 0

    def test_generate_default_params(self):
        candles = generate_synthetic_candles()
        assert len(candles) == 8760  # 1 year of hourly candles
        assert candles[0].open_time.year == 2025
        assert candles[0].symbol == "BTCUSD"
        assert candles[0].exchange == "bitfinex"
        assert candles[0].timeframe == "1h"
