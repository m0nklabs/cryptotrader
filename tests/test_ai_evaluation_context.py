"""Evaluation context and fail-closed behaviour (issue #432).

The Multi-Brain UI used to send only a symbol and a timeframe, so role output
could look actionable while carrying no market structure, holdings or risk
limits. These tests pin the two guarantees that make that impossible:

* no current market series -> the providers are never called and the answer is
  ``NEUTRAL`` with the reasons recorded;
* no current portfolio or risk limits -> roles may run, but the consensus is
  clamped to ``NEUTRAL`` and marked ``abstained``.

Both are asserted at the HTTP boundary, plus the pure classifier in
:mod:`core.ai.context`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from core.ai.context import CONTEXT_VERSION, build_evaluation_context
from core.ai.types import ConsensusDecision, ProviderName, RoleName, RoleVerdict

_BUDGET_OK = {
    "exceeded": False,
    "daily_exceeded": False,
    "monthly_exceeded": False,
    "daily_limit": 10.0,
    "monthly_limit": 100.0,
    "daily_spent": 0.0,
    "monthly_spent": 0.0,
}

_NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _candles(count: int = 3, *, close_time: datetime | None = None) -> list[dict]:
    """Build closed candles whose last close time is ``close_time``."""
    close_time = close_time or _NOW
    candles = []
    for index in range(count):
        bar_close = close_time - timedelta(hours=count - 1 - index)
        candles.append(
            {
                "open_time": (bar_close - timedelta(hours=1)).isoformat(),
                "close_time": bar_close.isoformat(),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "volume": 10.0,
            }
        )
    return candles


# ---------------------------------------------------------------------------
# Unit tests - classifier
# ---------------------------------------------------------------------------


def test_fresh_context_is_executable() -> None:
    """Current market data, portfolio and risk limits permit a real verdict."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=_NOW,
        portfolio={"total_value": 10000.0, "cash_balance": 5000.0},
        portfolio_as_of=_NOW - timedelta(minutes=1),
        risk_limits={"max_order_notional": 1000.0},
    )

    assert context.version == CONTEXT_VERSION
    assert context.can_run is True
    assert context.executable_ready is True
    assert context.abstain_reasons == []
    assert [item.name for item in context.inputs] == ["candles", "portfolio", "risk_limits"]


def test_missing_candles_block_the_evaluation() -> None:
    """No market series -> the pipeline has nothing to reason about."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=[],
        portfolio={"total_value": 1.0},
        portfolio_as_of=_NOW,
        risk_limits={"max_order_notional": 1.0},
    )

    assert context.can_run is False
    assert context.executable_ready is False
    assert context.missing == ["candles"]
    assert any("candles" in reason for reason in context.abstain_reasons)


def test_stale_candles_block_the_evaluation() -> None:
    """A series older than the freshness budget is not evidence."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        max_age_seconds=3600,
        candles=_candles(close_time=_NOW - timedelta(hours=5)),
        candles_as_of=_NOW - timedelta(hours=5),
        portfolio={"total_value": 1.0},
        portfolio_as_of=_NOW,
        risk_limits={"max_order_notional": 1.0},
    )

    assert context.can_run is False
    assert "candles" in context.stale
    assert any("stale" in reason for reason in context.abstain_reasons)


def test_undated_candles_are_not_trusted() -> None:
    """Freshness cannot be proven without a timestamp -> fail closed."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=None,
    )

    assert context.can_run is False
    assert any("timestamp" in reason for reason in context.abstain_reasons)


def test_future_timestamp_is_rejected() -> None:
    """A clock-skewed timestamp is unusable evidence."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=_NOW + timedelta(hours=2),
    )

    assert context.can_run is False
    assert any("future" in reason for reason in context.abstain_reasons)


def test_missing_portfolio_degrades_but_does_not_block() -> None:
    """Roles may still be asked, but the consensus cannot be executable."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=_NOW,
        portfolio=None,
        risk_limits={"max_order_notional": 1.0},
    )

    assert context.can_run is True
    assert context.executable_ready is False
    assert context.missing == ["portfolio"]


def test_missing_risk_limits_degrades_but_does_not_block() -> None:
    """Risk limits are configuration; without them no executable verdict."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=_NOW,
        portfolio={"total_value": 1.0},
        portfolio_as_of=_NOW,
        risk_limits={},
    )

    assert context.can_run is True
    assert context.executable_ready is False
    assert context.missing == ["risk_limits"]


def test_risk_limits_need_no_timestamp() -> None:
    """Configuration carries no observation time and must not be flagged stale."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=_NOW,
        portfolio={"total_value": 1.0},
        portfolio_as_of=_NOW,
        risk_limits={"max_order_notional": 500.0},
        risk_limits_as_of=None,
    )

    assert context.executable_ready is True


def test_snapshot_serialises_to_json() -> None:
    """The snapshot travels in the HTTP response, so it must be JSON-safe."""
    context = build_evaluation_context(
        symbol="BTC/USD",
        timeframe="1h",
        now=_NOW,
        candles=_candles(),
        candles_as_of=_NOW,
        portfolio={"total_value": 1.0},
        portfolio_as_of=_NOW,
    )

    payload = json.loads(json.dumps(context.to_dict()))

    assert payload["version"] == CONTEXT_VERSION
    assert payload["executable_ready"] is False
    assert {item["name"] for item in payload["inputs"]} == {"candles", "portfolio", "risk_limits"}


# ---------------------------------------------------------------------------
# API tests - fail-closed behaviour at the HTTP boundary
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_budget_check():
    """Budget lookups must not need a database."""
    with patch(
        "api.routes.ai.ai_crud.check_budget_exceeded",
        new_callable=AsyncMock,
        return_value=_BUDGET_OK,
    ):
        yield


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_ai_router():
    """LLMRouter double that always answers BUY."""

    async def mock_evaluate(symbol, timeframe, **kwargs):
        return ConsensusDecision(
            final_action="BUY",
            final_confidence=0.75,
            verdicts=[
                RoleVerdict(
                    role=RoleName.SCREENER,
                    action="BUY",
                    confidence=0.8,
                    reasoning="mock",
                )
            ],
            reasoning="mock evaluation",
            total_cost_usd=0.01,
            total_latency_ms=120.0,
        )

    router = Mock()
    router.evaluate_opportunity = AsyncMock(side_effect=mock_evaluate)
    router.get_usage_log.return_value = []
    router.clear_usage_log.return_value = None
    return router


@pytest.fixture
def crud_mocks():
    """Patch decision persistence and expose the log mock."""
    async def mock_log_decision(db, **kwargs):  # noqa: ANN001 - mirrors the CRUD signature
        return Mock(created_at=datetime.now(timezone.utc))

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routes.ai._get_session_factory", return_value=lambda: session), patch(
        "api.routes.ai.ai_crud.log_decision_with_usage",
        side_effect=mock_log_decision,
    ) as log_decision:
        yield log_decision


def _post_evaluate(client: TestClient, mock_ai_router: Mock, payload: dict):
    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        return client.post("/api/ai/evaluate", json=payload)


def test_abstains_without_market_data(client, mock_ai_router, crud_mocks) -> None:
    """Empty candle store -> NEUTRAL, no provider call, reasons recorded."""
    with patch(
        "api.routes.ai._load_market_context",
        new_callable=AsyncMock,
        return_value=([], None),
    ), patch(
        "api.routes.ai._load_portfolio_context",
        new_callable=AsyncMock,
        return_value=({"total_value": 1000.0}, _NOW),
    ):
        response = _post_evaluate(client, mock_ai_router, {"symbol": "BTC/USD", "timeframe": "1h"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finalAction"] == "NEUTRAL"
    assert body["finalConfidence"] == 0.0
    assert body["abstained"] is True
    assert body["verdicts"] == []
    assert any("candles" in reason for reason in body["abstainReasons"])
    assert body["context"]["can_run"] is False
    mock_ai_router.evaluate_opportunity.assert_not_called()


def test_stale_market_data_never_reaches_a_provider(client, mock_ai_router, crud_mocks) -> None:
    """A stale series is refused exactly like a missing one."""
    stale = _NOW - timedelta(days=3)
    with patch(
        "api.routes.ai._load_market_context",
        new_callable=AsyncMock,
        return_value=(_candles(close_time=stale), stale),
    ), patch(
        "api.routes.ai._load_portfolio_context",
        new_callable=AsyncMock,
        return_value=({"total_value": 1000.0}, _NOW),
    ):
        response = _post_evaluate(
            client,
            mock_ai_router,
            {"symbol": "BTC/USD", "timeframe": "1h", "maxContextAgeS": 3600},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finalAction"] == "NEUTRAL"
    assert body["abstained"] is True
    assert "candles" in body["context"]["stale"]
    mock_ai_router.evaluate_opportunity.assert_not_called()


def test_missing_risk_limits_clamp_the_consensus(client, mock_ai_router, crud_mocks) -> None:
    """Roles may answer, but a BUY without risk limits is not executable."""
    now = datetime.now(timezone.utc)
    with patch(
        "api.routes.ai._load_market_context",
        new_callable=AsyncMock,
        return_value=(_candles(close_time=now), now),
    ), patch(
        "api.routes.ai._load_portfolio_context",
        new_callable=AsyncMock,
        return_value=({"total_value": 1000.0}, now),
    ):
        response = _post_evaluate(client, mock_ai_router, {"symbol": "BTC/USD", "timeframe": "1h"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finalAction"] == "NEUTRAL"
    assert body["finalConfidence"] == 0.0
    assert body["abstained"] is True
    assert any("risk_limits" in reason for reason in body["abstainReasons"])
    assert "Abstained" in body["reasoning"]
    mock_ai_router.evaluate_opportunity.assert_called_once()


def test_complete_context_keeps_an_executable_verdict(client, mock_ai_router, crud_mocks) -> None:
    """All inputs current: the provider's BUY survives."""
    now = datetime.now(timezone.utc)
    with patch(
        "api.routes.ai._load_market_context",
        new_callable=AsyncMock,
        return_value=(_candles(close_time=now), now),
    ), patch(
        "api.routes.ai._load_portfolio_context",
        new_callable=AsyncMock,
        return_value=({"total_value": 1000.0}, now),
    ):
        response = _post_evaluate(
            client,
            mock_ai_router,
            {
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "riskLimits": {"max_order_notional": 500.0},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finalAction"] == "BUY"
    assert body["abstained"] is False
    assert body["abstainReasons"] == []
    assert body["context"]["executable_ready"] is True
    assert body["context"]["market_symbol"] == "BTCUSD"


def test_server_context_reaches_the_router(client, mock_ai_router, crud_mocks) -> None:
    """The assembled snapshot, not the request body, feeds the pipeline."""
    now = datetime.now(timezone.utc)
    candles = _candles(close_time=now)
    with patch(
        "api.routes.ai._load_market_context",
        new_callable=AsyncMock,
        return_value=(candles, now),
    ), patch(
        "api.routes.ai._load_portfolio_context",
        new_callable=AsyncMock,
        return_value=({"total_value": 42.0}, now),
    ):
        _post_evaluate(
            client,
            mock_ai_router,
            {
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "riskLimits": {"max_order_notional": 500.0},
                "candles": [{"close": 1.0}],
            },
        )

    call_kwargs = mock_ai_router.evaluate_opportunity.call_args.kwargs
    assert call_kwargs["candles"] == candles
    assert call_kwargs["portfolio"] == {"total_value": 42.0}


def test_legacy_path_without_context_build_is_unchanged(client, mock_ai_router, crud_mocks) -> None:
    """Explicit opt-out keeps the old contract and reports no snapshot."""
    response = _post_evaluate(
        client,
        mock_ai_router,
        {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "buildContext": False,
            "riskLimits": {"max_order_notional": 500.0},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finalAction"] == "BUY"
    assert body["context"] is None
    assert body["abstained"] is False


def test_role_failures_are_reported(client, mock_ai_router, crud_mocks) -> None:
    """A failed role is visible in the response instead of vanishing."""
    now = datetime.now(timezone.utc)
    mock_ai_router.get_usage_log.return_value = [
        Mock(
            role=RoleName.SCREENER,
            provider=ProviderName.DEEPSEEK,
            model="deepseek-chat",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.0,
            latency_ms=10.0,
            symbol="BTCUSD",
            success=False,
            error="timeout",
        )
    ]
    with patch(
        "api.routes.ai._load_market_context",
        new_callable=AsyncMock,
        return_value=(_candles(close_time=now), now),
    ), patch(
        "api.routes.ai._load_portfolio_context",
        new_callable=AsyncMock,
        return_value=({"total_value": 1000.0}, now),
    ):
        response = _post_evaluate(
            client,
            mock_ai_router,
            {
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "riskLimits": {"max_order_notional": 500.0},
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["roleFailures"] == [
        {
            "role": "screener",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "error": "timeout",
        }
    ]
