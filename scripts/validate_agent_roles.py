#!/usr/bin/env python
"""Validation script for agent role implementations.

Validates that each role implementation meets the acceptance criteria:
1. Each role produces a valid RoleVerdict with confidence 0.0-1.0
2. Screener processes symbols efficiently with pre-filtering
3. Tactical provides entry/exit levels
4. Fundamental handles news/sentiment data
5. Strategist implements VETO logic
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from core.ai.roles.fundamental import FundamentalRole
from core.ai.roles.screener import ScreenerRole
from core.ai.roles.strategist import StrategistRole
from core.ai.roles.tactical import TacticalRole
from core.ai.types import AIRequest, AIResponse, ProviderName, RoleName
from core.types import Candle


def validate_verdict(verdict, role_name: str, required_metrics: list[str] | None = None):
    """Validate a RoleVerdict meets basic requirements."""
    print(f"\n✓ {role_name} verdict validation:")
    print(f"  - Role: {verdict.role.value}")
    print(f"  - Action: {verdict.action}")
    print(f"  - Confidence: {verdict.confidence}")
    
    assert 0.0 <= verdict.confidence <= 1.0, f"Confidence out of range: {verdict.confidence}"
    assert verdict.action in ["BUY", "SELL", "NEUTRAL", "VETO"], f"Invalid action: {verdict.action}"
    assert len(verdict.reasoning) > 0, "Reasoning is empty"
    
    if required_metrics:
        for metric in required_metrics:
            assert metric in verdict.metrics, f"Missing required metric: {metric}"
            print(f"  - Metric '{metric}': {verdict.metrics[metric]}")
    
    print(f"  ✓ All validations passed for {role_name}")


def test_screener_validation():
    """Test Screener role with batch processing."""
    print("\n" + "="*60)
    print("SCREENER ROLE VALIDATION")
    print("="*60)
    
    screener = ScreenerRole()
    
    # Create test data with mix of good and bad symbols
    symbols = [
        "BTC/USD",  # Good volume
        "ETH/USD",  # Low volume - should be filtered
        "SOL/USD",  # Good
        "DOGE/USD",  # Extreme RSI - should be filtered
    ]
    
    indicators = {
        "BTC/USD": {"volume_24h": 1000000000, "rsi": 55, "bb_upper": 51000, "bb_middle": 50000, "bb_lower": 49000},
        "ETH/USD": {"volume_24h": 50000, "rsi": 50, "bb_upper": 3100, "bb_middle": 3000, "bb_lower": 2900},
        "SOL/USD": {"volume_24h": 500000000, "rsi": 45, "bb_upper": 105, "bb_middle": 100, "bb_lower": 95},
        "DOGE/USD": {"volume_24h": 200000000, "rsi": 98, "bb_upper": 0.12, "bb_middle": 0.10, "bb_lower": 0.08},
    }
    
    request = AIRequest(
        role=RoleName.SCREENER,
        user_prompt="Find the best trading opportunities",
        context={
            "symbols": symbols,
            "timeframe": "1h",
            "indicators": indicators,
        },
    )
    
    # Test quick-reject logic
    print("\nTesting quick-reject heuristics:")
    for symbol in symbols:
        should_reject, reason = screener._quick_reject(symbol, indicators[symbol])
        status = "REJECTED" if should_reject else "PASSED"
        print(f"  - {symbol}: {status}" + (f" ({reason})" if should_reject else ""))
    
    # Test prompt building
    prompt = screener.build_prompt(request)
    assert len(prompt) > 100, "Prompt too short"
    assert "JSON" in prompt, "Missing JSON format instructions"
    print(f"\n✓ Screener prompt generated ({len(prompt)} chars)")
    
    # Test response parsing with mock response
    mock_response = AIResponse(
        role=RoleName.SCREENER,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-chat",
        raw_text="Screening complete",
        parsed={
            "action": "BUY",
            "confidence": 0.7,
            "reasoning": "BTC and SOL show strong momentum",
            "filtered_symbols": ["BTC/USD", "SOL/USD"],
            "strong_buy_symbols": ["BTC/USD"],
        },
    )
    
    verdict = screener.parse_response(mock_response)
    validate_verdict(verdict, "Screener", required_metrics=["symbols_passed", "strong_buy_count"])
    
    print("\n✓ Screener validation PASSED")


def test_tactical_validation():
    """Test Tactical role with price analysis."""
    print("\n" + "="*60)
    print("TACTICAL ROLE VALIDATION")
    print("="*60)
    
    tactical = TacticalRole()
    
    # Create sample candle data
    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(100):
        close_price = Decimal("50000") + Decimal(i * 50)
        candles.append(
            Candle(
                symbol="BTC/USD",
                exchange="binance",
                timeframe="1h",
                open_time=base_time.replace(hour=i % 24),
                close_time=base_time.replace(hour=(i + 1) % 24),
                open=close_price - Decimal("25"),
                high=close_price + Decimal("50"),
                low=close_price - Decimal("50"),
                close=close_price,
                volume=Decimal("1000"),
            )
        )
    
    indicators = {
        "rsi": 55.5,
        "macd": {"line": 120.5, "signal": 115.0, "histogram": 5.5},
        "bb_upper": 55500.0,
        "bb_middle": 54950.0,
        "bb_lower": 54400.0,
    }
    
    request = AIRequest(
        role=RoleName.TACTICAL,
        user_prompt="Analyze price action and provide entry/exit levels",
        context={
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "candles": candles,
            "indicators": indicators,
        },
    )
    
    # Test support/resistance calculation
    sr_levels = tactical._calculate_support_resistance(candles)
    print("\nSupport/Resistance Levels:")
    print(f"  - Current Price: ${sr_levels['current_price']:,.2f}")
    print(f"  - Resistance: ${sr_levels['resistance']:,.2f} (+{sr_levels['resistance_distance_pct']:.2f}%)")
    print(f"  - Support: ${sr_levels['support']:,.2f} (-{sr_levels['support_distance_pct']:.2f}%)")
    
    # Test prompt building
    prompt = tactical.build_prompt(request)
    assert "PRICE DATA" in prompt, "Missing price data section"
    assert "INDICATOR VALUES" in prompt, "Missing indicators section"
    assert "SUPPORT/RESISTANCE" in prompt, "Missing S/R levels"
    print(f"\n✓ Tactical prompt generated ({len(prompt)} chars)")
    
    # Test response parsing with price levels
    mock_response = AIResponse(
        role=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-reasoner",
        raw_text="Bullish breakout pattern",
        parsed={
            "action": "BUY",
            "confidence": 0.85,
            "reasoning": "Strong uptrend with MACD confirmation",
            "entry": 54950.0,
            "stop_loss": 54400.0,
            "take_profit": 56050.0,
        },
    )
    
    verdict = tactical.parse_response(mock_response)
    validate_verdict(verdict, "Tactical", required_metrics=["entry", "stop_loss", "take_profit", "risk_reward"])
    
    # Validate risk/reward calculation
    rr_ratio = verdict.metrics["risk_reward"]
    print(f"  - Risk/Reward Ratio: {rr_ratio:.2f}")
    assert rr_ratio == 2.0, f"Expected R/R of 2.0, got {rr_ratio}"
    
    print("\n✓ Tactical validation PASSED")


def test_fundamental_validation():
    """Test Fundamental role with news/sentiment."""
    print("\n" + "="*60)
    print("FUNDAMENTAL ROLE VALIDATION")
    print("="*60)
    
    fundamental = FundamentalRole()
    
    news_data = [
        {"title": "Bitcoin ETF approved by SEC", "source": "Bloomberg", "timestamp": "2024-01-01T10:00:00Z"},
        {"title": "Major institutional adoption announced", "source": "CoinDesk", "timestamp": "2024-01-01T12:00:00Z"},
    ]
    
    request = AIRequest(
        role=RoleName.FUNDAMENTAL,
        user_prompt="Assess fundamental outlook",
        context={
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "news": news_data,
        },
    )
    
    # Test news parsing
    parsed_news = fundamental._parse_news_items(news_data)
    print(f"\nParsed {len(parsed_news)} news items:")
    for item in parsed_news:
        print(f"  - {item['title']}")
    
    # Test sentiment calculation
    response_text = "Very bullish sentiment with positive regulatory news and growing institutional adoption"
    sentiment_metrics = fundamental._calculate_sentiment_score(parsed_news, response_text)
    print(f"\nSentiment Metrics:")
    print(f"  - News Count: {sentiment_metrics['news_count']}")
    print(f"  - Sentiment Score: {sentiment_metrics['sentiment_score']:.2f}")
    print(f"  - Event Risk: {sentiment_metrics['event_risk']:.2f}")
    
    # Test prompt building
    prompt = fundamental.build_prompt(request)
    assert "fundamental analysis" in prompt.lower(), "Missing fundamental analysis instructions"
    assert "sentiment" in prompt.lower(), "Missing sentiment instructions"
    print(f"\n✓ Fundamental prompt generated ({len(prompt)} chars)")
    
    # Test response parsing
    mock_response = AIResponse(
        role=RoleName.FUNDAMENTAL,
        provider=ProviderName.XAI,
        model="grok-4",
        raw_text="Positive fundamental outlook",
        parsed={
            "action": "BUY",
            "confidence": 0.75,
            "reasoning": "Strong positive news flow with regulatory clarity",
            "sentiment_score": 0.7,
            "event_risk": 0.1,
            "social_volume": 0.8,
            "key_events": ["ETF approval", "Institutional adoption"],
        },
    )
    
    verdict = fundamental.parse_response(mock_response)
    validate_verdict(verdict, "Fundamental", required_metrics=["sentiment_score", "event_risk", "key_events_count"])
    
    print("\n✓ Fundamental validation PASSED")


def test_strategist_validation():
    """Test Strategist role with risk management."""
    print("\n" + "="*60)
    print("STRATEGIST ROLE VALIDATION")
    print("="*60)
    
    strategist = StrategistRole()
    
    # Test data: portfolio at risk limits
    positions = [
        {"symbol": "BTC/USD", "side": "LONG", "quantity": Decimal("0.5"), 
         "avg_entry_price": Decimal("50000"), "notional": Decimal("25000"), "unrealized_pnl": Decimal("1000")},
        {"symbol": "ETH/USD", "side": "LONG", "quantity": Decimal("5.0"), 
         "avg_entry_price": Decimal("3000"), "notional": Decimal("15000"), "unrealized_pnl": Decimal("500")},
    ]
    
    portfolio = {"total_equity": 100000.0, "available_balance": 60000.0}
    risk_limits = {"max_positions": 3, "max_exposure_pct": 0.8, "max_risk_per_trade_pct": 0.02}
    
    # Test 1: Normal trade (should pass)
    print("\nTest 1: Normal trade within limits")
    proposed_trade = {"size": 1.0, "entry_price": 100.0, "stop_loss": 98.0}
    
    from core.ai.roles.base import format_portfolio_state
    portfolio_state = format_portfolio_state(positions, 100000.0, 60000.0)
    
    should_veto, reason = strategist._check_risk_limits(proposed_trade, portfolio_state, risk_limits)
    print(f"  - VETO: {should_veto}" + (f" ({reason})" if should_veto else " (Trade approved)"))
    assert not should_veto, "Trade should not be vetoed"
    
    # Test 2: Exceeding max positions
    print("\nTest 2: Exceeding max positions")
    risk_limits_strict = {"max_positions": 2, "max_exposure_pct": 0.8, "max_risk_per_trade_pct": 0.02}
    should_veto, reason = strategist._check_risk_limits(proposed_trade, portfolio_state, risk_limits_strict)
    print(f"  - VETO: {should_veto} ({reason})")
    assert should_veto, "Trade should be vetoed for max positions"
    
    # Test 3: Position sizing
    print("\nTest 3: Position sizing calculation")
    sizing = strategist._suggest_position_size(proposed_trade, portfolio_state, risk_limits)
    print(f"  - Kelly Fraction: {sizing['kelly_fraction']:.2%}")
    print(f"  - Fixed Fraction: {sizing['fixed_fraction']:.2%}")
    print(f"  - Recommended Size: {sizing['recommended_size']:.4f}")
    assert sizing["recommended_size"] > 0, "Position size should be positive"
    
    # Test 4: Correlation check
    print("\nTest 4: Correlation penalty")
    corr_score = strategist._calculate_correlation_penalty("BTC/EUR", positions)
    print(f"  - Correlation Score (BTC/EUR with BTC/USD): {corr_score:.2f}")
    assert corr_score > 0, "Should detect correlation with existing BTC position"
    
    # Test with uncorrelated asset
    corr_score_uncorr = strategist._calculate_correlation_penalty("SOL/USD", positions)
    print(f"  - Correlation Score (SOL/USD with BTC/ETH): {corr_score_uncorr:.2f}")
    assert corr_score > corr_score_uncorr, "BTC should have higher correlation than SOL"
    
    # Test 5: Response parsing with VETO
    print("\nTest 5: VETO response parsing")
    mock_response = AIResponse(
        role=RoleName.STRATEGIST,
        provider=ProviderName.OPENAI,
        model="o3-mini",
        raw_text="Trade vetoed due to risk",
        parsed={
            "action": "VETO",
            "confidence": 1.0,
            "reasoning": "Would exceed maximum portfolio exposure limit",
            "veto_reason": "Max exposure breached",
        },
    )
    
    verdict = strategist.parse_response(mock_response)
    assert verdict.action == "VETO", "Should parse VETO action"
    assert verdict.confidence == 1.0, "VETO should have high confidence"
    print(f"  ✓ VETO correctly parsed: {verdict.reasoning}")
    
    print("\n✓ Strategist validation PASSED")


def main():
    """Run all validation tests."""
    print("\n" + "="*60)
    print("AGENT ROLE IMPLEMENTATION VALIDATION")
    print("="*60)
    
    try:
        test_screener_validation()
        test_tactical_validation()
        test_fundamental_validation()
        test_strategist_validation()
        
        print("\n" + "="*60)
        print("ALL VALIDATIONS PASSED ✓")
        print("="*60)
        print("\nSummary:")
        print("  ✓ Screener: Batch processing with quick-reject filters")
        print("  ✓ Tactical: Entry/exit levels with support/resistance")
        print("  ✓ Fundamental: News parsing and sentiment scoring")
        print("  ✓ Strategist: VETO logic and position sizing")
        print("\nAll acceptance criteria met!")
        
    except AssertionError as e:
        print(f"\n✗ VALIDATION FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
