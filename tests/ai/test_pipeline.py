"""Integration tests for the full Multi-Brain AI pipeline.

Tests the complete flow: Symbol → Router → All Roles → Consensus → Decision
with mocked providers to validate audit chain, cost aggregation, and decision logic.

Part of issue #209 (P6) for #205 Multi-Brain AI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.ai.consensus import ConsensusEngine
from core.ai.roles.base import RoleRegistry
from core.ai.router import LLMRouter
from core.ai.types import (
    AIResponse,
    ProviderName,
    RoleConfig,
    RoleName,
    RoleVerdict,
)


# ---------------------------------------------------------------------------
# Full Pipeline Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_all_roles_agree_buy():
    """Test complete pipeline when all roles agree on BUY."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Register all 4 roles with BUY consensus
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL, RoleName.FUNDAMENTAL, RoleName.STRATEGIST]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        async def mock_eval(*args, **kwargs):
            return (
                AIResponse(
                    role=role_name,
                    provider=ProviderName.DEEPSEEK,
                    model="test",
                    raw_text='{"action": "BUY"}',
                    parsed={"action": "BUY"},
                    tokens_in=100,
                    tokens_out=50,
                    cost_usd=0.002,
                    latency_ms=300.0,
                ),
                RoleVerdict(
                    role=role_name,
                    action="BUY",
                    confidence=0.85,
                    reasoning=f"{role_name.value} analysis: strong buy signal",
                ),
            )
        
        mock_role.evaluate = mock_eval
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Verify final decision
    assert decision.final_action == "BUY"
    assert decision.final_confidence > 0.8
    assert decision.vetoed_by is None
    
    # Verify all verdicts included
    assert len(decision.verdicts) == 4
    assert all(v.action == "BUY" for v in decision.verdicts)
    
    # Verify cost aggregation
    assert decision.total_cost_usd == pytest.approx(0.008, rel=1e-4)  # 4 roles * 0.002
    
    # Verify latency tracking (wall-clock, not sum)
    assert decision.total_latency_ms > 0
    assert decision.total_latency_ms < 2000  # Parallel execution


@pytest.mark.asyncio
async def test_full_pipeline_mixed_signals():
    """Test pipeline with mixed signals from different roles."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Different actions per role
    role_actions = {
        RoleName.SCREENER: ("BUY", 0.7),
        RoleName.TACTICAL: ("BUY", 0.8),
        RoleName.FUNDAMENTAL: ("NEUTRAL", 0.6),
        RoleName.STRATEGIST: ("SELL", 0.5),
    }
    
    for role_name, (action, conf) in role_actions.items():
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        # Use closure to capture action and conf
        def make_eval(rn, act, c):
            async def mock_eval(*args, **kwargs):
                return (
                    AIResponse(
                        role=rn,
                        provider=ProviderName.DEEPSEEK,
                        model="test",
                        raw_text=f'{{"action": "{act}"}}',
                        cost_usd=0.002,
                    ),
                    RoleVerdict(
                        role=rn,
                        action=act,
                        confidence=c,
                        reasoning=f"{rn.value}: {act}",
                    ),
                )
            return mock_eval
        
        mock_role.evaluate = make_eval(role_name, action, conf)
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # With 2 BUY, 1 NEUTRAL, 1 SELL, BUY should win
    # But confidence should be lower due to disagreement
    assert decision.final_action in ["BUY", "NEUTRAL"]  # Depends on weights and thresholds
    assert len(decision.verdicts) == 4
    
    # All roles should be represented
    verdict_roles = {v.role for v in decision.verdicts}
    assert verdict_roles == set(role_actions.keys())


@pytest.mark.asyncio
async def test_full_pipeline_with_veto():
    """Test pipeline when Strategist issues VETO."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Most roles vote BUY
    role_actions = {
        RoleName.SCREENER: ("BUY", 0.9),
        RoleName.TACTICAL: ("BUY", 0.95),
        RoleName.FUNDAMENTAL: ("BUY", 0.8),
        RoleName.STRATEGIST: ("VETO", 1.0),  # VETO overrides
    }
    
    for role_name, (action, conf) in role_actions.items():
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        def make_eval(rn, act, c):
            async def mock_eval(*args, **kwargs):
                return (
                    AIResponse(
                        role=rn,
                        provider=ProviderName.DEEPSEEK,
                        model="test",
                        raw_text=f'{{"action": "{act}"}}',
                        cost_usd=0.003,
                    ),
                    RoleVerdict(
                        role=rn,
                        action=act,
                        confidence=c,
                        reasoning=f"{rn.value}: {act} - Maximum risk limit reached",
                    ),
                )
            return mock_eval
        
        mock_role.evaluate = make_eval(role_name, action, conf)
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # VETO should override BUY consensus
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert decision.vetoed_by == RoleName.STRATEGIST
    assert "VETOED" in decision.reasoning or "veto" in decision.reasoning.lower()


@pytest.mark.asyncio
async def test_full_pipeline_with_role_failure():
    """Test pipeline resilience when one role fails."""
    router = LLMRouter(consensus_engine=ConsensusEngine(), min_roles_required=2)
    
    # 3 roles succeed, 1 fails
    for i, role_name in enumerate([RoleName.SCREENER, RoleName.TACTICAL, RoleName.FUNDAMENTAL, RoleName.STRATEGIST]):
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        if i == 0:  # First role fails
            async def failing_eval(*args, **kwargs):
                raise Exception("Provider timeout")
            mock_role.evaluate = failing_eval
        else:
            def make_eval(rn):
                async def mock_eval(*args, **kwargs):
                    return (
                        AIResponse(
                            role=rn,
                            provider=ProviderName.DEEPSEEK,
                            model="test",
                            raw_text='{"action": "BUY"}',
                            cost_usd=0.002,
                        ),
                        RoleVerdict(
                            role=rn,
                            action="BUY",
                            confidence=0.8,
                            reasoning=f"{rn.value}: BUY",
                        ),
                    )
                return mock_eval
            mock_role.evaluate = make_eval(role_name)
        
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Should still get BUY decision from 3 successful roles
    assert decision.final_action == "BUY"
    assert len(decision.verdicts) == 3  # Only successful roles
    
    # Partial evaluation note should be present
    assert "Partial evaluation" in decision.reasoning or "failed" in decision.reasoning.lower()
    
    # Cost should only include successful roles
    assert decision.total_cost_usd == pytest.approx(0.006, rel=1e-4)


@pytest.mark.asyncio
async def test_full_pipeline_all_roles_fail():
    """Test pipeline when all roles fail (should return NEUTRAL)."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # All roles fail
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL, RoleName.FUNDAMENTAL, RoleName.STRATEGIST]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        async def failing_eval(*args, **kwargs):
            raise Exception("All providers down")
        
        mock_role.evaluate = failing_eval
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Should return NEUTRAL with no verdicts
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert len(decision.verdicts) == 0
    assert decision.total_cost_usd == 0.0
    assert "Insufficient roles" in decision.reasoning


# ---------------------------------------------------------------------------
# Audit Chain Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_chain_complete():
    """Test that full audit chain is captured in decision."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Register 2 roles for minimal test
    for role_name in [RoleName.TACTICAL, RoleName.FUNDAMENTAL]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK if role_name == RoleName.TACTICAL else ProviderName.XAI,
            model="test-model",
            system_prompt_id="test-prompt",
            enabled=True,
        )
        
        def make_eval(rn, prov):
            async def mock_eval(*args, **kwargs):
                return (
                    AIResponse(
                        role=rn,
                        provider=prov,
                        model="test-model",
                        raw_text='{"action": "BUY"}',
                        tokens_in=100,
                        tokens_out=50,
                        cost_usd=0.002,
                        latency_ms=250.0,
                    ),
                    RoleVerdict(
                        role=rn,
                        action="BUY",
                        confidence=0.8,
                        reasoning=f"{rn.value} reasoning",
                    ),
                )
            return mock_eval
        
        provider = ProviderName.DEEPSEEK if role_name == RoleName.TACTICAL else ProviderName.XAI
        mock_role.evaluate = make_eval(role_name, provider)
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Verify audit trail
    assert len(decision.verdicts) == 2
    
    # Check each verdict has complete info
    for verdict in decision.verdicts:
        assert verdict.role in [RoleName.TACTICAL, RoleName.FUNDAMENTAL]
        assert verdict.action == "BUY"
        assert verdict.confidence == 0.8
        assert verdict.reasoning is not None
    
    # Check aggregated metrics
    assert decision.total_cost_usd > 0
    assert decision.total_latency_ms > 0


@pytest.mark.asyncio
async def test_usage_log_tracking():
    """Test that router tracks usage log for audit."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    router.clear_usage_log()
    
    # Register one role
    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )
    
    async def mock_eval(*args, **kwargs):
        return (
            AIResponse(
                role=RoleName.TACTICAL,
                provider=ProviderName.DEEPSEEK,
                model="test",
                raw_text="{}",
                tokens_in=150,
                tokens_out=75,
                cost_usd=0.003,
                latency_ms=400.0,
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.8,
                reasoning="test",
            ),
        )
    
    mock_role.evaluate = mock_eval
    RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Check usage log
    usage_log = router.get_usage_log()
    assert len(usage_log) == 1
    
    entry = usage_log[0]
    assert entry.role == RoleName.TACTICAL
    assert entry.provider == ProviderName.DEEPSEEK
    assert entry.tokens_in == 150
    assert entry.tokens_out == 75
    assert entry.cost_usd == 0.003
    assert entry.success is True


# ---------------------------------------------------------------------------
# Cost Aggregation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_aggregation_different_providers():
    """Test cost aggregation when roles use different providers."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Different providers with different costs
    provider_costs = {
        RoleName.SCREENER: (ProviderName.DEEPSEEK, 0.001),
        RoleName.TACTICAL: (ProviderName.DEEPSEEK, 0.002),
        RoleName.FUNDAMENTAL: (ProviderName.XAI, 0.005),
        RoleName.STRATEGIST: (ProviderName.OPENAI, 0.010),
    }
    
    for role_name, (provider, cost) in provider_costs.items():
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=provider,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        def make_eval(rn, prov, c):
            async def mock_eval(*args, **kwargs):
                return (
                    AIResponse(
                        role=rn,
                        provider=prov,
                        model="test",
                        raw_text="{}",
                        cost_usd=c,
                    ),
                    RoleVerdict(
                        role=rn,
                        action="BUY",
                        confidence=0.8,
                        reasoning="test",
                    ),
                )
            return mock_eval
        
        mock_role.evaluate = make_eval(role_name, provider, cost)
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Total should be sum of all costs
    expected_total = sum(cost for _, cost in provider_costs.values())
    assert abs(decision.total_cost_usd - expected_total) < 0.000001
    assert decision.total_cost_usd == pytest.approx(0.018, rel=1e-4)


@pytest.mark.asyncio
async def test_cost_aggregation_with_ollama_free():
    """Test that Ollama (local, free) doesn't add to cost."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Mix of paid and free providers
    provider_costs = {
        RoleName.TACTICAL: (ProviderName.DEEPSEEK, 0.002),
        RoleName.FUNDAMENTAL: (ProviderName.OLLAMA, 0.0),  # Free
    }
    
    for role_name, (provider, cost) in provider_costs.items():
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=provider,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )
        
        def make_eval(rn, prov, c):
            async def mock_eval(*args, **kwargs):
                return (
                    AIResponse(
                        role=rn,
                        provider=prov,
                        model="test",
                        raw_text="{}",
                        cost_usd=c,
                    ),
                    RoleVerdict(
                        role=rn,
                        action="BUY",
                        confidence=0.8,
                        reasoning="test",
                    ),
                )
            return mock_eval
        
        mock_role.evaluate = make_eval(role_name, provider, cost)
        RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
    
    # Total should only include paid provider
    assert decision.total_cost_usd == pytest.approx(0.002, rel=1e-4)


# ---------------------------------------------------------------------------
# Symbol and Timeframe Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_different_symbols():
    """Test pipeline with different trading symbols."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Register minimal role
    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )
    
    async def mock_eval(symbol, *args, **kwargs):
        # Return different actions based on symbol
        action = "BUY" if "BTC" in symbol else "SELL"
        return (
            AIResponse(
                role=RoleName.TACTICAL,
                provider=ProviderName.DEEPSEEK,
                model="test",
                raw_text=f'{{"action": "{action}"}}',
                cost_usd=0.002,
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action=action,
                confidence=0.8,
                reasoning=f"Analysis for {symbol}",
            ),
        )
    
    mock_role.evaluate = mock_eval
    RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        # Test BTC
        btc_decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )
        
        # Test ETH
        eth_decision = await router.evaluate_opportunity(
            symbol="ETH/USD",
            timeframe="1h",
        )
    
    # Different symbols should get different decisions
    assert "BTC" in btc_decision.verdicts[0].reasoning
    assert "ETH" in eth_decision.verdicts[0].reasoning


@pytest.mark.asyncio
async def test_pipeline_different_timeframes():
    """Test pipeline with different timeframes."""
    router = LLMRouter(consensus_engine=ConsensusEngine())
    
    # Register minimal role
    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )
    
    async def mock_eval(symbol, timeframe, *args, **kwargs):
        return (
            AIResponse(
                role=RoleName.TACTICAL,
                provider=ProviderName.DEEPSEEK,
                model="test",
                raw_text='{"action": "BUY"}',
                cost_usd=0.002,
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.8,
                reasoning=f"Analysis on {timeframe} timeframe",
            ),
        )
    
    mock_role.evaluate = mock_eval
    RoleRegistry.register(mock_role)
    
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        # Test different timeframes
        for tf in ["5m", "15m", "1h", "4h", "1d"]:
            decision = await router.evaluate_opportunity(
                symbol="BTC/USD",
                timeframe=tf,
            )
            
            assert tf in decision.verdicts[0].reasoning
