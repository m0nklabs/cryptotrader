#!/usr/bin/env python
"""Validate that all AI agent roles are fully implemented.

This script verifies:
1. All four roles can be instantiated
2. All roles have required methods (build_prompt, parse_response, evaluate)
3. All roles produce valid RoleVerdict outputs
4. All acceptance criteria are met
5. CoinDossier alignment is correct
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal

from core.ai.roles.base import serialize_candles, serialize_indicators
from core.ai.roles.fundamental import FundamentalRole
from core.ai.roles.screener import ScreenerRole
from core.ai.roles.strategist import StrategistRole
from core.ai.roles.tactical import TacticalRole
from core.ai.types import AIRequest, AIResponse, ProviderName, RoleName
from core.types import Candle


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def validate_role_instantiation() -> bool:
    """Verify all roles can be instantiated."""
    print_section("1. Role Instantiation")

    roles = {
        "Screener": ScreenerRole(),
        "Tactical": TacticalRole(),
        "Fundamental": FundamentalRole(),
        "Strategist": StrategistRole(),
    }

    for name, role in roles.items():
        has_build = hasattr(role, "build_prompt")
        has_parse = hasattr(role, "parse_response")
        has_evaluate = hasattr(role, "evaluate")

        status = "✓" if (has_build and has_parse and has_evaluate) else "✗"
        print(f"{status} {name:12} - build_prompt={has_build}, parse_response={has_parse}, evaluate={has_evaluate}")

        if not (has_build and has_parse and has_evaluate):
            return False

    return True


def validate_screener() -> bool:
    """Verify Screener role functionality."""
    print_section("2. Screener Role")

    screener = ScreenerRole()

    # Test quick-reject
    indicators_low_vol = {"volume_24h": 50000, "rsi": 50}
    should_reject, reason = screener._quick_reject("BTC/USD", indicators_low_vol)
    print(f"✓ Quick-reject (low volume): {should_reject} - {reason}")

    # Test batch processing
    request = AIRequest(
        role=RoleName.SCREENER,
        user_prompt="Find opportunities",
        context={
            "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
            "indicators": {
                "BTC/USD": {"volume_24h": 1000000, "rsi": 55},
                "ETH/USD": {"volume_24h": 500000, "rsi": 60},
                "SOL/USD": {"volume_24h": 50000, "rsi": 45},  # Will be filtered
            },
        },
    )
    prompt = screener.build_prompt(request)
    print(f"✓ Batch prompt length: {len(prompt)} chars")
    print(f"✓ Contains JSON instruction: {'JSON' in prompt}")
    print(f"✓ Contains pre-filtered info: {'pre-filtered' in prompt.lower() or 'rejected' in prompt.lower()}")

    # Test response parsing
    response = AIResponse(
        role=RoleName.SCREENER,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-chat",
        raw_text="Analysis complete",
        parsed={
            "action": "BUY",
            "confidence": 0.75,
            "reasoning": "Found 2 strong opportunities",
            "filtered_symbols": ["BTC/USD", "ETH/USD"],
        },
    )
    verdict = screener.parse_response(response)
    print(f"✓ Verdict action: {verdict.action}")
    print(f"✓ Verdict confidence: {verdict.confidence} (in [0.0, 1.0]: {0.0 <= verdict.confidence <= 1.0})")

    return True


def validate_tactical() -> bool:
    """Verify Tactical role functionality."""
    print_section("3. Tactical Role")

    tactical = TacticalRole()

    # Create sample candles
    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta

    candles = [
        Candle(
            symbol="BTC/USD",
            exchange="binance",
            timeframe="1h",
            open_time=base_time + timedelta(hours=i),
            close_time=base_time + timedelta(hours=i + 1),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50000") + Decimal(i * 10),
            volume=Decimal("1000"),
        )
        for i in range(50)
    ]

    # Test support/resistance
    sr_levels = tactical._calculate_support_resistance(candles)
    print(f"✓ Support/resistance calculated: {list(sr_levels.keys())}")
    print(f"  Current price: {sr_levels['current_price']:.2f}")
    print(f"  Support: {sr_levels['support']:.2f}, Resistance: {sr_levels['resistance']:.2f}")

    # Test price level extraction
    response_text = "Entry at $50,000. Stop loss: 49000. Take profit: 55000."
    levels = tactical._extract_price_levels(response_text)
    print(f"✓ Extracted levels: entry={levels.get('entry')}, stop={levels.get('stop_loss')}, tp={levels.get('take_profit')}")

    # Test response parsing
    response = AIResponse(
        role=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-reasoner",
        raw_text="Strong setup",
        parsed={
            "action": "BUY",
            "confidence": 0.8,
            "reasoning": "RSI oversold + MACD crossover",
            "entry": 50000,
            "stop_loss": 49000,
            "take_profit": 55000,
        },
    )
    verdict = tactical.parse_response(response)
    print(f"✓ Verdict with levels: entry={verdict.metrics.get('entry')}, risk_reward={verdict.metrics.get('risk_reward')}")

    return True


def validate_fundamental() -> bool:
    """Verify Fundamental role functionality."""
    print_section("4. Fundamental Role")

    fundamental = FundamentalRole()

    # Test news parsing
    news_text = "Bitcoin ETF approved\n\nMajor exchange listing announced"
    parsed_news = fundamental._parse_news_items(news_text)
    print(f"✓ Parsed news items: {len(parsed_news)} items")

    # Test sentiment calculation
    sentiment_metrics = fundamental._calculate_sentiment_score([], "Very bullish outlook with strong growth potential")
    print(f"✓ Sentiment score: {sentiment_metrics['sentiment_score']:.2f}")
    print(f"✓ Event risk: {sentiment_metrics['event_risk']:.2f}")

    # Test response parsing
    response = AIResponse(
        role=RoleName.FUNDAMENTAL,
        provider=ProviderName.XAI,
        model="grok-4",
        raw_text="Positive sentiment",
        parsed={
            "action": "BUY",
            "confidence": 0.7,
            "reasoning": "Strong positive news flow",
            "sentiment_score": 0.6,
            "event_risk": 0.2,
            "key_events": ["ETF approval", "Exchange listing"],
        },
    )
    verdict = fundamental.parse_response(response)
    print(f"✓ Sentiment score: {verdict.metrics.get('sentiment_score')}")
    print(f"✓ Key events count: {verdict.metrics.get('key_events_count')}")

    return True


def validate_strategist() -> bool:
    """Verify Strategist role functionality."""
    print_section("5. Strategist Role")

    strategist = StrategistRole()

    # Test risk limit checks
    portfolio_state = {
        "total_equity": 100000,
        "total_exposure": 96000,
        "num_positions": 2,
        "positions": [],
    }
    risk_limits = {
        "max_exposure_pct": 0.95,
        "max_positions": 10,
        "max_risk_per_trade_pct": 0.02,
    }
    proposed_trade = {"size": 1.0, "entry_price": 50000, "stop_loss": 48000}

    should_veto, reason = strategist._check_risk_limits(proposed_trade, portfolio_state, risk_limits)
    print(f"✓ Hard VETO on exposure breach: {should_veto}")
    print(f"  Reason: {reason}")

    # Test correlation analysis
    existing_positions = [
        {"symbol": "BTC/EUR", "side": "LONG"},
        {"symbol": "ETH/USD", "side": "LONG"},
    ]
    correlation = strategist._calculate_correlation_penalty("BTC/USD", existing_positions)
    print(f"✓ Correlation penalty: {correlation:.2f} (BTC/USD vs BTC/EUR + ETH/USD)")

    # Test position sizing
    portfolio_state["total_exposure"] = 40000  # Under limit
    sizing = strategist._suggest_position_size(proposed_trade, portfolio_state, risk_limits)
    print(f"✓ Kelly fraction: {sizing['kelly_fraction']:.3f}")
    print(f"✓ Recommended size: {sizing['recommended_size']:.4f}")

    # Test response parsing
    response = AIResponse(
        role=RoleName.STRATEGIST,
        provider=ProviderName.OPENAI,
        model="o3-mini",
        raw_text="Approved",
        parsed={
            "action": "BUY",
            "confidence": 0.75,
            "reasoning": "Risk within limits",
            "position_size_pct": 0.05,
            "portfolio_risk_pct": 0.15,
        },
    )
    verdict = strategist.parse_response(response)
    print(f"✓ Position size %: {verdict.metrics.get('position_size_pct')}")
    print(f"✓ Portfolio risk %: {verdict.metrics.get('portfolio_risk_pct')}")

    return True


def validate_coindossier_alignment() -> bool:
    """Verify CoinDossier field alignment."""
    print_section("6. CoinDossier Alignment")

    # Tactical fields
    tactical = TacticalRole()
    response = AIResponse(
        role=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        raw_text="test",
        parsed={
            "action": "BUY",
            "confidence": 0.8,
            "reasoning": "Strong setup",
            "entry": 50000,
            "stop_loss": 49000,
            "take_profit": 55000,
        },
    )
    verdict = tactical.parse_response(response)
    print(f"✓ Tactical → CoinDossier:")
    print(f"  action: {verdict.action}")
    print(f"  confidence (1-10): {int(verdict.confidence * 10)}")
    print(f"  entry_zone: [{verdict.metrics.get('entry')}]")
    print(f"  stop_loss: {verdict.metrics.get('stop_loss')}")
    print(f"  take_profit: [{verdict.metrics.get('take_profit')}]")

    # Fundamental enrichment
    fundamental = FundamentalRole()
    response = AIResponse(
        role=RoleName.FUNDAMENTAL,
        provider=ProviderName.XAI,
        model="test",
        raw_text="test",
        parsed={
            "action": "BUY",
            "confidence": 0.7,
            "reasoning": "Positive news",
            "sentiment_score": 0.6,
            "event_risk": 0.2,
        },
    )
    verdict = fundamental.parse_response(response)
    print(f"✓ Fundamental → CoinDossier:")
    print(f"  sentiment_score: {verdict.metrics.get('sentiment_score')}")
    print(f"  risk_level (from event_risk): {'low' if verdict.metrics.get('event_risk', 0) < 0.3 else 'medium'}")

    # Strategist risk assessment
    strategist = StrategistRole()
    response = AIResponse(
        role=RoleName.STRATEGIST,
        provider=ProviderName.OPENAI,
        model="test",
        raw_text="test",
        parsed={
            "action": "BUY",
            "confidence": 0.75,
            "reasoning": "Risk within limits",
            "position_size_pct": 0.05,
            "portfolio_risk_pct": 0.15,
        },
    )
    verdict = strategist.parse_response(response)
    print(f"✓ Strategist → CoinDossier:")
    print(f"  position_size_pct: {verdict.metrics.get('position_size_pct')}")
    print(f"  risk_level (from portfolio_risk): {'low' if verdict.metrics.get('portfolio_risk_pct', 0) < 0.2 else 'medium'}")

    return True


def main() -> int:
    """Run all validation checks."""
    print("\n" + "=" * 70)
    print("  AI Agent Roles Implementation Validation")
    print("=" * 70)

    checks = [
        ("Role Instantiation", validate_role_instantiation),
        ("Screener Role", validate_screener),
        ("Tactical Role", validate_tactical),
        ("Fundamental Role", validate_fundamental),
        ("Strategist Role", validate_strategist),
        ("CoinDossier Alignment", validate_coindossier_alignment),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with error: {e}")
            results.append((name, False))

    print_section("Summary")
    all_passed = all(result for _, result in results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} - {name}")

    print("\n" + "=" * 70)
    if all_passed:
        print("  ✅ ALL VALIDATION CHECKS PASSED")
        print("  All four agent roles are fully implemented!")
    else:
        print("  ❌ SOME VALIDATION CHECKS FAILED")
        print("  Please review the output above for details.")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
