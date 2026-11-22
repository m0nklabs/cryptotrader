"""Tests for open-position equity accounting in the backtest engine (issue #431).

The equity curve must mark the open position to market on every candle, the
intra-trade excursion must reach max drawdown, and the run must state what it
does with a position that is still open on the last candle.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.backtest.engine import END_OF_RUN_POLICIES, BacktestEngine
from core.backtest.strategy import Signal
from core.types import Candle

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
INITIAL_CAPITAL = 10000.0


def make_candles(closes: list[str]) -> list[Candle]:
    """Build hourly candles whose close prices are the given decimal strings."""
    candles: list[Candle] = []
    for i, close in enumerate(closes):
        price = Decimal(close)
        candles.append(
            Candle(
                exchange="bitfinex",
                symbol="BTCUSD",
                timeframe="1h",
                open_time=START + timedelta(hours=i),
                close_time=START + timedelta(hours=i + 1),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal("1"),
            )
        )
    return candles


class ScriptedStrategy:
    """Returns a pre-scripted signal per candle; extra candles yield None."""

    def __init__(self, sides: list[str | None]):
        self._sides = list(sides)
        self._index = 0

    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        if self._index >= len(self._sides):
            return None
        side = self._sides[self._index]
        self._index += 1
        if side is None:
            return None
        return Signal(side=side, strength=1)


def run(closes: list[str], sides: list[str | None], **engine_kwargs):
    engine = BacktestEngine(candle_store=None, initial_capital=INITIAL_CAPITAL, **engine_kwargs)
    return engine.run(strategy=ScriptedStrategy(sides), candles=make_candles(closes))


# ========== Mark-to-market of an open position ==========


def test_long_open_position_is_marked_to_market() -> None:
    result = run(["100", "105", "110"], ["BUY", None, None])

    assert result.equity_curve == [INITIAL_CAPITAL, 10000.0, 10005.0, 10010.0]
    assert result.total_pnl == pytest.approx(10.0)
    assert result.realized_pnl == pytest.approx(0.0)
    assert result.unrealized_pnl == pytest.approx(10.0)
    assert result.trades == []
    assert result.open_position is not None
    assert result.open_position["side"] == "LONG"
    assert result.open_position["entry_price"] == pytest.approx(100.0)
    assert result.open_position["mark_price"] == pytest.approx(110.0)
    assert result.open_position["unrealized_pnl"] == pytest.approx(10.0)


def test_long_adverse_excursion_reaches_drawdown() -> None:
    result = run(["100", "90"], ["BUY", None])

    assert result.equity_curve == [INITIAL_CAPITAL, 10000.0, 9990.0]
    assert result.total_pnl == pytest.approx(-10.0)
    assert result.unrealized_pnl == pytest.approx(-10.0)
    assert result.trades == []
    # The 1% dip is only visible because equity is marked to market.
    assert result.max_drawdown == pytest.approx(0.001)


def test_short_open_position_is_marked_to_market() -> None:
    result = run(["100", "90"], ["SELL", None])

    assert result.equity_curve == [INITIAL_CAPITAL, 10000.0, 10010.0]
    assert result.total_pnl == pytest.approx(10.0)
    assert result.unrealized_pnl == pytest.approx(10.0)
    assert result.open_position is not None
    assert result.open_position["side"] == "SHORT"


def test_short_adverse_excursion_reaches_drawdown() -> None:
    result = run(["100", "110"], ["SELL", None])

    assert result.equity_curve == [INITIAL_CAPITAL, 10000.0, 9990.0]
    assert result.total_pnl == pytest.approx(-10.0)
    assert result.max_drawdown == pytest.approx(0.001)


# ========== End-of-run policy ==========


def test_default_policy_marks_the_final_open_position() -> None:
    result = run(["100", "105"], ["BUY", None])

    assert result.end_of_run_policy == "mark_to_market"
    assert result.open_position is not None
    assert result.unrealized_pnl == pytest.approx(5.0)


def test_force_close_liquidates_the_final_long() -> None:
    result = run(["100", "105"], ["BUY", None], end_of_run_policy="force_close")

    assert result.end_of_run_policy == "force_close"
    assert len(result.trades) == 1
    assert result.trades[0].side == "BUY"
    assert result.trades[0].pnl == Decimal("5")
    assert result.total_pnl == pytest.approx(5.0)
    assert result.realized_pnl == pytest.approx(5.0)
    assert result.unrealized_pnl == pytest.approx(0.0)
    assert result.open_position is None
    assert result.equity_curve[-1] == pytest.approx(INITIAL_CAPITAL + 5.0)
    assert result.win_rate == pytest.approx(1.0)


def test_force_close_liquidates_the_final_short() -> None:
    result = run(["100", "90"], ["SELL", None], end_of_run_policy="force_close")

    assert len(result.trades) == 1
    assert result.trades[0].side == "SELL"
    assert result.trades[0].pnl == Decimal("10")
    assert result.total_pnl == pytest.approx(10.0)
    assert result.open_position is None


def test_invalid_end_of_run_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="end_of_run_policy"):
        BacktestEngine(candle_store=None, end_of_run_policy="hold_forever")


def test_supported_policies_are_stable() -> None:
    assert END_OF_RUN_POLICIES == ("mark_to_market", "force_close")


# ========== Consistency ==========


def test_realized_plus_unrealized_equals_total_pnl() -> None:
    result = run(["100", "110", "105", "115"], ["BUY", "SELL", "BUY", None])

    assert len(result.trades) == 2
    assert result.realized_pnl == pytest.approx(15.0)
    assert result.unrealized_pnl == pytest.approx(10.0)
    assert result.total_pnl == pytest.approx(25.0)
    assert result.total_pnl == pytest.approx(result.realized_pnl + result.unrealized_pnl)
    assert result.equity_curve[-1] == pytest.approx(INITIAL_CAPITAL + 25.0)


def test_flat_book_has_no_open_position() -> None:
    result = run(["100", "101", "102"], [None, None, None])

    assert result.open_position is None
    assert result.unrealized_pnl == pytest.approx(0.0)
    assert result.total_pnl == pytest.approx(0.0)
    assert result.equity_curve == [INITIAL_CAPITAL, 10000.0, 10000.0, 10000.0]


def test_empty_candle_series_is_flat() -> None:
    engine = BacktestEngine(candle_store=None, initial_capital=INITIAL_CAPITAL)
    result = engine.run(strategy=ScriptedStrategy([]), candles=[])

    assert result.equity_curve == [INITIAL_CAPITAL]
    assert result.total_pnl == pytest.approx(0.0)
    assert result.open_position is None
    assert result.trades == []