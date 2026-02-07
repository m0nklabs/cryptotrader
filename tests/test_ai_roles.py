"""Unit tests for AI agent role implementations.

Tests business logic, prompt building, response parsing, and helper functions
for all four agent roles: Screener, Tactical, Fundamental, Strategist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.ai.roles.base import (
    calculate_position_size_kelly,
    calculate_risk_metrics,
    format_portfolio_state,
    serialize_candles,
    serialize_indicators,
)
from core.ai.roles.fundamental import FundamentalRole
from core.ai.roles.screener import ScreenerRole
from core.ai.roles.strategist import StrategistRole
from core.ai.roles.tactical import TacticalRole
from core.ai.types import AIRequest, AIResponse, ProviderName, RoleName
from core.types import Candle


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_candles():
    """Generate sample candle data for testing."""
    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(100):
        close_price = Decimal("50000") + Decimal(i * 100)
        candles.append(
            Candle(
                symbol="BTC/USD",
                exchange="binance",
                timeframe="1h",
                open_time=base_time.replace(hour=i % 24),
                close_time=base_time.replace(hour=(i + 1) % 24),
                open=close_price - Decimal("50"),
                high=close_price + Decimal("100"),
                low=close_price - Decimal("100"),
                close=close_price,
                volume=Decimal("1000"),
            )
        )
    return candles


@pytest.fixture
def sample_indicators():
    """Generate sample indicator data for testing."""
    return {
        "rsi": 45.5,
        "macd": {"line": 120.5, "signal": 115.0, "histogram": 5.5},
        "bb_upper": 51000.0,
        "bb_middle": 50000.0,
        "bb_lower": 49000.0,
        "volume_24h": 500000000.0,
        "atr": 250.0,
    }


@pytest.fixture
def sample_portfolio_positions():
    """Generate sample portfolio positions for testing."""
    return [
        {
            "symbol": "BTC/USD",
            "side": "LONG",
            "quantity": Decimal("0.5"),
            "avg_entry_price": Decimal("50000"),
            "unrealized_pnl": Decimal("1000"),
            "notional": Decimal("25000"),
        },
        {
            "symbol": "ETH/USD",
            "side": "LONG",
            "quantity": Decimal("5.0"),
            "avg_entry_price": Decimal("3000"),
            "unrealized_pnl": Decimal("500"),
            "notional": Decimal("15000"),
        },
    ]


# ---------------------------------------------------------------------------
# Base Helper Function Tests
# ---------------------------------------------------------------------------


def test_serialize_candles_compact(sample_candles):
    """Test compact candle serialization (close prices only)."""
    result = serialize_candles(sample_candles, max_candles=10, include_full_data=False)
    
    assert len(result) == 10
    assert all("time" in c and "close" in c for c in result)
    assert all("open" not in c for c in result)
    assert isinstance(result[0]["close"], float)


def test_serialize_candles_full(sample_candles):
    """Test full candle serialization (all OHLCV data)."""
    result = serialize_candles(sample_candles, max_candles=5, include_full_data=True)
    
    assert len(result) == 5
    assert all("open" in c and "high" in c and "low" in c for c in result)
    assert all("close" in c and "volume" in c for c in result)


def test_serialize_candles_empty():
    """Test serialization with empty candle list."""
    result = serialize_candles([])
    assert result == []


def test_serialize_indicators(sample_indicators):
    """Test indicator serialization with Decimal conversion."""
    indicators_with_decimals = {
        "rsi": Decimal("45.5"),
        "price": Decimal("50000.123"),
        "nested": {"value": Decimal("100.5")},
        "list_values": [Decimal("1.1"), Decimal("2.2")],
    }
    
    result = serialize_indicators(indicators_with_decimals)
    
    assert isinstance(result["rsi"], float)
    assert isinstance(result["price"], float)
    assert isinstance(result["nested"]["value"], float)
    assert all(isinstance(v, float) for v in result["list_values"])


def test_format_portfolio_state(sample_portfolio_positions):
    """Test portfolio state formatting."""
    result = format_portfolio_state(
        sample_portfolio_positions,
        total_equity=100000.0,
        available_balance=60000.0,
    )
    
    assert result["total_equity"] == 100000.0
    assert result["available_balance"] == 60000.0
    assert result["num_positions"] == 2
    assert result["total_exposure"] == 40000.0
    assert len(result["positions"]) == 2


def test_calculate_position_size_kelly():
    """Test Kelly criterion position sizing."""
    # Favorable scenario
    size = calculate_position_size_kelly(
        win_rate=0.6, avg_win=0.05, avg_loss=0.02, max_kelly_fraction=0.25
    )
    assert 0.0 < size <= 0.25
    
    # Unfavorable scenario (should return 0)
    size = calculate_position_size_kelly(
        win_rate=0.3, avg_win=0.02, avg_loss=0.05, max_kelly_fraction=0.25
    )
    assert size == 0.0
    
    # Edge case: no loss (should return 0)
    size = calculate_position_size_kelly(
        win_rate=0.6, avg_win=0.05, avg_loss=0.0, max_kelly_fraction=0.25
    )
    assert size == 0.0


def test_calculate_risk_metrics():
    """Test risk metric calculations."""
    metrics = calculate_risk_metrics(
        proposed_size=1.0,
        entry_price=50000.0,
        stop_loss=49000.0,
        total_equity=100000.0,
        max_risk_per_trade=0.02,
    )
    
    assert metrics["notional"] == 50000.0
    assert metrics["risk_per_unit"] == 1000.0
    assert metrics["total_risk"] == 1000.0
    assert metrics["risk_pct"] == 0.01  # 1% of equity
    assert not metrics["exceeds_limit"]
    
    # Test exceeding limit
    metrics = calculate_risk_metrics(
        proposed_size=5.0,
        entry_price=50000.0,
        stop_loss=49000.0,
        total_equity=100000.0,
        max_risk_per_trade=0.02,
    )
    assert metrics["exceeds_limit"]


# ---------------------------------------------------------------------------
# Screener Role Tests
# ---------------------------------------------------------------------------


def test_screener_quick_reject_low_volume():
    """Test screener quick-reject for low volume."""
    screener = ScreenerRole()
    indicators = {"volume_24h": 50000, "rsi": 50}
    
    should_reject, reason = screener._quick_reject("BTC/USD", indicators)
    
    assert should_reject
    assert "volume" in reason.lower()


def test_screener_quick_reject_extreme_rsi():
    """Test screener quick-reject for extreme RSI."""
    screener = ScreenerRole()
    
    # Extremely overbought
    indicators = {"volume_24h": 1000000, "rsi": 96}
    should_reject, reason = screener._quick_reject("BTC/USD", indicators)
    assert should_reject
    assert "overbought" in reason.lower()
    
    # Extremely oversold
    indicators = {"volume_24h": 1000000, "rsi": 4}
    should_reject, reason = screener._quick_reject("BTC/USD", indicators)
    assert should_reject
    assert "oversold" in reason.lower()


def test_screener_quick_reject_tight_bollinger():
    """Test screener quick-reject for tight Bollinger Bands."""
    screener = ScreenerRole()
    indicators = {
        "volume_24h": 1000000,
        "rsi": 50,
        "bb_upper": 50100,
        "bb_middle": 50000,
        "bb_lower": 49900,
    }
    
    should_reject, reason = screener._quick_reject("BTC/USD", indicators)
    
    assert should_reject
    assert "volatility" in reason.lower()


def test_screener_build_prompt():
    """Test screener prompt building."""
    screener = ScreenerRole()
    request = AIRequest(
        role=RoleName.SCREENER,
        user_prompt="Find trading opportunities",
        context={
            "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
            "timeframe": "1h",
            "indicators": {
                "BTC/USD": {"volume_24h": 1000000, "rsi": 45},
                "ETH/USD": {"volume_24h": 50000, "rsi": 50},  # Low volume
                "SOL/USD": {"volume_24h": 500000, "rsi": 55},
            },
        },
    )
    
    prompt = screener.build_prompt(request)
    
    assert "BTC/USD" in prompt
    assert "SOL/USD" in prompt
    assert "ETH/USD" in prompt  # Shown in rejected list
    assert "pre-filtered" in prompt.lower() or "rejected" in prompt.lower()
    assert "JSON" in prompt


@pytest.mark.asyncio
async def test_screener_parse_response_success():
    """Test screener response parsing with valid JSON."""
    screener = ScreenerRole()
    response = AIResponse(
        role=RoleName.SCREENER,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-chat",
        raw_text="Analysis complete",
        parsed={
            "action": "BUY",
            "confidence": 0.75,
            "reasoning": "Found 2 strong opportunities",
            "filtered_symbols": ["BTC/USD", "SOL/USD"],
            "strong_buy_symbols": ["BTC/USD"],
        },
    )
    
    verdict = screener.parse_response(response)
    
    assert verdict.role == RoleName.SCREENER
    assert verdict.action == "BUY"
    assert verdict.confidence == 0.75
    assert verdict.metrics["symbols_passed"] == 2.0
    assert verdict.metrics["strong_buy_count"] == 1.0


@pytest.mark.asyncio
async def test_screener_parse_response_error():
    """Test screener response parsing with error."""
    screener = ScreenerRole()
    response = AIResponse(
        role=RoleName.SCREENER,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-chat",
        raw_text="",
        error="API timeout",
    )
    
    verdict = screener.parse_response(response)
    
    assert verdict.action == "NEUTRAL"
    assert verdict.confidence == 0.0
    assert "error" in verdict.reasoning.lower()


# ---------------------------------------------------------------------------
# Tactical Role Tests
# ---------------------------------------------------------------------------


def test_tactical_calculate_support_resistance(sample_candles):
    """Test support/resistance level calculation."""
    tactical = TacticalRole()
    sr_levels = tactical._calculate_support_resistance(sample_candles, lookback=50)
    
    assert "current_price" in sr_levels
    assert "resistance" in sr_levels
    assert "support" in sr_levels
    assert sr_levels["resistance"] > sr_levels["current_price"]
    assert sr_levels["support"] < sr_levels["current_price"]


def test_tactical_extract_price_levels():
    """Test price level extraction from LLM response text."""
    tactical = TacticalRole()
    response_text = """
    Based on the analysis:
    - Entry: $50000
    - Stop Loss: 48500
    - Take Profit: 55000
    The risk/reward ratio is favorable.
    """
    
    levels = tactical._extract_price_levels(response_text)
    
    assert levels["entry"] == 50000.0
    assert levels["stop_loss"] == 48500.0
    assert levels["take_profit"] == 55000.0


def test_tactical_build_prompt(sample_candles, sample_indicators):
    """Test tactical prompt building."""
    tactical = TacticalRole()
    request = AIRequest(
        role=RoleName.TACTICAL,
        user_prompt="Analyze price action",
        context={
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "candles": sample_candles,
            "indicators": sample_indicators,
        },
    )
    
    prompt = tactical.build_prompt(request)
    
    assert "BTC/USD" in prompt
    assert "1h" in prompt
    assert "PRICE DATA" in prompt
    assert "INDICATOR VALUES" in prompt
    assert "SUPPORT/RESISTANCE" in prompt
    assert "JSON" in prompt


@pytest.mark.asyncio
async def test_tactical_parse_response_with_levels():
    """Test tactical response parsing with price levels."""
    tactical = TacticalRole()
    response = AIResponse(
        role=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-reasoner",
        raw_text="Strong bullish signal",
        parsed={
            "action": "BUY",
            "confidence": 0.85,
            "reasoning": "Bullish MACD crossover with RSI confirmation",
            "entry": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
        },
    )
    
    verdict = tactical.parse_response(response)
    
    assert verdict.action == "BUY"
    assert verdict.confidence == 0.85
    assert verdict.metrics["entry"] == 50000.0
    assert verdict.metrics["stop_loss"] == 49000.0
    assert verdict.metrics["take_profit"] == 52000.0
    assert "risk_reward" in verdict.metrics
    assert verdict.metrics["risk_reward"] == 2.0  # (52000-50000)/(50000-49000)


@pytest.mark.asyncio
async def test_tactical_parse_response_fallback_extraction():
    """Test tactical response parsing with text extraction fallback."""
    tactical = TacticalRole()
    response = AIResponse(
        role=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-reasoner",
        raw_text="Entry at $50000, stop loss 49000, target 55000",
        parsed=None,  # No structured response
    )
    
    verdict = tactical.parse_response(response)
    
    assert "entry" in verdict.metrics
    assert verdict.metrics["entry"] == 50000.0


# ---------------------------------------------------------------------------
# Fundamental Role Tests
# ---------------------------------------------------------------------------


def test_fundamental_parse_news_items_structured():
    """Test news item parsing with structured input."""
    fundamental = FundamentalRole()
    news_data = [
        {"title": "Bitcoin reaches new high", "source": "CoinDesk", "timestamp": "2024-01-01T00:00:00Z"},
        {"title": "SEC approves ETF", "source": "Bloomberg", "timestamp": "2024-01-01T12:00:00Z"},
    ]
    
    items = fundamental._parse_news_items(news_data)
    
    assert len(items) == 2
    assert items[0]["title"] == "Bitcoin reaches new high"


def test_fundamental_parse_news_items_text():
    """Test news item parsing with unstructured text."""
    fundamental = FundamentalRole()
    news_text = """
    1. Bitcoin reaches new all-time high
    
    2. Major exchange lists new token
    
    3. Regulatory clarity in Europe
    """
    
    items = fundamental._parse_news_items(news_text)
    
    assert len(items) > 0
    assert all("title" in item for item in items)


def test_fundamental_calculate_sentiment_score():
    """Test sentiment score calculation."""
    fundamental = FundamentalRole()
    news_items = [
        {"title": "Bullish outlook for crypto", "source": "test"},
        {"title": "Positive adoption trends", "source": "test"},
    ]
    response_text = "The overall sentiment is bullish with positive growth indicators and no major bearish concerns."
    
    metrics = fundamental._calculate_sentiment_score(news_items, response_text)
    
    assert metrics["news_count"] == 2.0
    assert metrics["sentiment_score"] > 0  # Should be positive
    assert "event_risk" in metrics


def test_fundamental_build_prompt():
    """Test fundamental prompt building."""
    fundamental = FundamentalRole()
    request = AIRequest(
        role=RoleName.FUNDAMENTAL,
        user_prompt="Assess market sentiment",
        context={
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "news": [
                {"title": "Major partnership announced", "source": "CoinDesk"},
            ],
        },
    )
    
    prompt = fundamental.build_prompt(request)
    
    assert "BTC/USD" in prompt
    assert "fundamental analysis" in prompt.lower()
    assert "news" in prompt.lower()
    assert "JSON" in prompt


@pytest.mark.asyncio
async def test_fundamental_parse_response_with_metrics():
    """Test fundamental response parsing with sentiment metrics."""
    fundamental = FundamentalRole()
    response = AIResponse(
        role=RoleName.FUNDAMENTAL,
        provider=ProviderName.XAI,
        model="grok-4",
        raw_text="Positive news sentiment",
        parsed={
            "action": "BUY",
            "confidence": 0.7,
            "reasoning": "Strong positive news flow with institutional adoption",
            "sentiment_score": 0.6,
            "event_risk": 0.2,
            "social_volume": 0.8,
            "key_events": ["ETF approval", "Major partnership"],
        },
    )
    
    verdict = fundamental.parse_response(response)
    
    assert verdict.action == "BUY"
    assert verdict.metrics["sentiment_score"] == 0.6
    assert verdict.metrics["event_risk"] == 0.2
    assert verdict.metrics["social_volume"] == 0.8
    assert verdict.metrics["key_events_count"] == 2.0


# ---------------------------------------------------------------------------
# Strategist Role Tests
# ---------------------------------------------------------------------------


def test_strategist_check_risk_limits_max_positions(sample_portfolio_positions):
    """Test strategist risk limit check for max positions."""
    strategist = StrategistRole()
    portfolio_state = format_portfolio_state(sample_portfolio_positions, 100000.0, 50000.0)
    risk_limits = {"max_positions": 2}
    proposed_trade = {}
    
    should_veto, reason = strategist._check_risk_limits(
        proposed_trade, portfolio_state, risk_limits
    )
    
    assert should_veto
    assert "position" in reason.lower()


def test_strategist_check_risk_limits_max_exposure(sample_portfolio_positions):
    """Test strategist risk limit check for max exposure."""
    strategist = StrategistRole()
    portfolio_state = format_portfolio_state(sample_portfolio_positions, 50000.0, 10000.0)
    risk_limits = {"max_exposure_pct": 0.5}  # 50% max
    proposed_trade = {}
    
    should_veto, reason = strategist._check_risk_limits(
        proposed_trade, portfolio_state, risk_limits
    )
    
    assert should_veto
    assert "exposure" in reason.lower()


def test_strategist_check_risk_limits_per_trade_risk():
    """Test strategist risk limit check for per-trade risk."""
    strategist = StrategistRole()
    portfolio_state = {"total_equity": 100000.0, "num_positions": 1, "total_exposure": 20000.0}
    risk_limits = {"max_risk_per_trade_pct": 0.01}  # 1% max
    proposed_trade = {
        "size": 2.0,
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
    }
    
    should_veto, reason = strategist._check_risk_limits(
        proposed_trade, portfolio_state, risk_limits
    )
    
    assert should_veto
    assert "risk" in reason.lower()


def test_strategist_calculate_correlation_penalty():
    """Test correlation penalty calculation."""
    strategist = StrategistRole()
    existing_positions = [
        {"symbol": "BTC/USD"},
        {"symbol": "BTC/EUR"},
        {"symbol": "ETH/USD"},
    ]
    
    # High correlation (same base asset)
    score = strategist._calculate_correlation_penalty("BTC/USDT", existing_positions)
    assert score > 0.5
    
    # Low correlation (different base asset)
    score = strategist._calculate_correlation_penalty("SOL/USD", existing_positions)
    assert score < 0.5


def test_strategist_suggest_position_size():
    """Test position size suggestion."""
    strategist = StrategistRole()
    portfolio_state = {"total_equity": 100000.0, "available_balance": 50000.0}
    risk_limits = {
        "historical_win_rate": 0.6,
        "avg_win_pct": 0.05,
        "avg_loss_pct": 0.02,
        "fixed_position_size_pct": 0.1,
    }
    proposed_trade = {"entry_price": 50000.0}
    
    sizing = strategist._suggest_position_size(proposed_trade, portfolio_state, risk_limits)
    
    assert "kelly_fraction" in sizing
    assert "recommended_size" in sizing
    assert sizing["recommended_size"] > 0


def test_strategist_build_prompt(sample_portfolio_positions):
    """Test strategist prompt building."""
    strategist = StrategistRole()
    request = AIRequest(
        role=RoleName.STRATEGIST,
        user_prompt="Evaluate trade risk",
        context={
            "symbol": "SOL/USD",
            "proposed_action": "BUY",
            "proposed_trade": {"size": 1.0, "entry_price": 100.0, "stop_loss": 95.0},
            "positions": sample_portfolio_positions,
            "portfolio": {"total_equity": 100000.0, "available_balance": 60000.0},
            "risk_limits": {"max_positions": 5, "max_risk_per_trade_pct": 0.02},
        },
    )
    
    prompt = strategist.build_prompt(request)
    
    assert "SOL/USD" in prompt
    assert "PORTFOLIO STATE" in prompt
    assert "RISK LIMITS" in prompt
    assert "CORRELATION" in prompt
    assert "POSITION SIZING" in prompt
    assert "JSON" in prompt


@pytest.mark.asyncio
async def test_strategist_parse_response_veto():
    """Test strategist response parsing with VETO."""
    strategist = StrategistRole()
    response = AIResponse(
        role=RoleName.STRATEGIST,
        provider=ProviderName.OPENAI,
        model="o3-mini",
        raw_text="Trade vetoed",
        parsed={
            "action": "VETO",
            "confidence": 1.0,
            "reasoning": "Exceeds max position limit",
            "veto_reason": "Maximum positions already open",
        },
    )
    
    verdict = strategist.parse_response(response)
    
    assert verdict.action == "VETO"
    assert verdict.confidence == 1.0


@pytest.mark.asyncio
async def test_strategist_parse_response_error_defaults_veto():
    """Test strategist defaults to VETO on error."""
    strategist = StrategistRole()
    response = AIResponse(
        role=RoleName.STRATEGIST,
        provider=ProviderName.OPENAI,
        model="o3-mini",
        raw_text="",
        error="Provider timeout",
    )
    
    verdict = strategist.parse_response(response)
    
    assert verdict.action == "VETO"
    assert verdict.confidence == 1.0
    assert "error" in verdict.reasoning.lower()


@pytest.mark.asyncio
async def test_strategist_parse_response_with_metrics():
    """Test strategist response parsing with risk metrics."""
    strategist = StrategistRole()
    response = AIResponse(
        role=RoleName.STRATEGIST,
        provider=ProviderName.OPENAI,
        model="o3-mini",
        raw_text="Approved with caution",
        parsed={
            "action": "BUY",
            "confidence": 0.6,
            "reasoning": "Trade is acceptable but watch correlation risk",
            "position_size_pct": 0.08,
            "portfolio_risk_pct": 0.015,
            "correlation_score": 0.4,
        },
    )
    
    verdict = strategist.parse_response(response)
    
    assert verdict.action == "BUY"
    assert verdict.metrics["position_size_pct"] == 0.08
    assert verdict.metrics["portfolio_risk_pct"] == 0.015
    assert verdict.metrics["correlation_score"] == 0.4
