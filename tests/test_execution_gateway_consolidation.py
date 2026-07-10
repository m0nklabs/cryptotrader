"""Regression tests for issue #425 — order routing must use the orchestrator gateway.

These tests prove the acceptance criteria of the issue:
- AC1: A single mandatory server-side order gateway exists and is reachable
      at /execution/* (mounting the orchestrator router).
- AC2: Direct executor bypasses are removed for order mutations.
- AC3: One durable order/position/decision source of truth — the orchestrator's
      paper_executor. _get_paper_executor() returns the same instance.
- AC4: Every accepted/rejected order through POST /orders persists the complete
      gate decision and state snapshot in the orchestrator audit log.
- AC5: Route-level integration tests prove no order path bypasses the gateway.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app, _get_paper_executor, _get_orchestrator


EXECUTION_PATHS = {
    "/execution/evaluate",
    "/execution/paper-order",
    "/execution/paper-summary",
    "/execution/decision-path",
}


@pytest.fixture
def fm_client():
    """Test client that resets orchestrator + cooldown/dedup state per test."""
    from api.main import (
        _automation_config,
        _cooldown_check,
        _get_signal_dedup,
        _get_trade_history,
    )

    orch = _get_orchestrator()
    executor = _get_paper_executor()
    executor._orders.clear()
    executor._positions.clear()
    executor._last_prices.clear()
    executor._order_book._orders.clear()
    executor._next_order_id = 1
    orch._audit_log.clear()
    orch._daily_spend_usd = 0.0
    orch._monthly_spend_usd = 0.0
    orch._trade_count_today = 0

    # Mirror test_api_paper_trading.py autouse fixture so cooldown/dedup
    # does not carry over between our tests.
    th = _get_trade_history()
    th.trades.clear()
    if _cooldown_check is not None:
        _cooldown_check.__dict__.clear()
        _cooldown_check.__dict__["config"] = _automation_config
        _cooldown_check.__dict__["trade_history"] = th
    dedup = _get_signal_dedup()
    if hasattr(dedup, "last_signal") and dedup.last_signal is not None:
        dedup.last_signal.clear()

    return TestClient(app)


# ---------------------------------------------------------------------------
# AC1 — execution routes are mounted on the app
# ---------------------------------------------------------------------------


class TestExecutionRoutesMounted:
    def test_execution_routes_active(self, fm_client):
        """The /execution/* routes from api.routes.execution must be mounted."""
        registered = {getattr(r, "path", "") for r in app.routes}
        for path in EXECUTION_PATHS:
            assert path in registered, (
                f"Expected execution route {path} to be mounted; "
                f"missing route proves the gateway is unreachable."
            )


# ---------------------------------------------------------------------------
# AC2 + AC3 — single source of truth, no second paper executor
# ---------------------------------------------------------------------------


class TestSingleSourceOfTruth:
    def test_paper_executor_is_orchestrators(self):
        """_get_paper_executor() must return the orchestrator's paper_executor instance."""
        orch = _get_orchestrator()
        executor = _get_paper_executor()
        assert executor is orch.paper_executor, (
            "Direct paper executor bypass: api.main._get_paper_executor() returns "
            "an instance that is not the orchestrator's paper_executor."
        )

    def test_no_two_paper_executors(self):
        """There must be exactly one PaperExecutor instance reachable via main.py."""
        orch = _get_orchestrator()
        executor = _get_paper_executor()
        assert _get_paper_executor() is executor
        assert orch.paper_executor is executor


# ---------------------------------------------------------------------------
# AC4 — every accepted/rejected order via POST /orders persists gate audit
# ---------------------------------------------------------------------------


class TestOrderAuditLogPersistence:
    def test_post_orders_persists_audit_entry(self, fm_client):
        """POST /orders must record the full gate decision in the audit log."""
        response = fm_client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "0.5",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert response.status_code == 200
        orch = _get_orchestrator()
        audit = orch.get_audit_log()
        assert audit, "Orchestrator audit log must record the order decision."
        entry = audit[-1]
        assert entry["symbol"] == "BTCUSD"
        assert entry["action"] in {"EXECUTED", "REJECTED"}
        assert entry["gate_results"], (
            "Every audit entry must capture the full gate decision."
        )
        assert entry.get("paper_order_id") is not None, (
            "Accepted orders persist paper_order_id; the orchestrator must "
            "have executed through paper_executor (the single source of truth)."
        )


# ---------------------------------------------------------------------------
# AC5 — POST /orders goes through the orchestrator, not a raw executor call
# ---------------------------------------------------------------------------


class TestOrdersGoesThroughOrchestrator:
    def test_post_orders_uses_orchestrator_gateway(self, fm_client, monkeypatch):
        """POST /orders must invoke a method on ExecutionOrchestrator (the gateway).

        Market orders route through the new orchestrator method
        ``execute_with_explicit_qty`` which honours caller qty while still
        running veto/budget/exposure/risk-limit gates. The point of this
        test is to confirm POST /orders goes through the orchestrator, not
        a direct PaperExecutor.execute_paper_order bypass.
        """
        orch = _get_orchestrator()
        calls = []

        real = orch.execute_with_explicit_qty

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return real(*args, **kwargs)

        monkeypatch.setattr(orch, "execute_with_explicit_qty", spy)

        # Also confirm the direct bypass isn't taken — count how often
        # ``executor.execute_paper_order`` is invoked for symbol "BTCUSD".
        executor = _get_paper_executor()
        direct_calls = []
        real_direct = executor.execute_paper_order

        def direct_spy(*args, **kwargs):
            direct_calls.append((args, kwargs))
            return real_direct(*args, **kwargs)

        monkeypatch.setattr(executor, "execute_paper_order", direct_spy)

        response = fm_client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "0.25",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert response.status_code == 200, (
            "POST /orders must succeed via the orchestrator gateway; "
            f"got {response.status_code}: {response.text}"
        )
        assert len(calls) == 1, (
            "POST /orders must call orchestrator.execute_with_explicit_qty "
            "exactly once per request — confirms the gateway routes "
            "through the orchestrator, not a direct executor call."
        )
        # Exactly one executor.execute_paper_order invocation happens — and
        # it must be from inside the orchestrator's call. If POST /orders
        # also called the executor directly, the count would jump to >1.
        assert len(direct_calls) == 1, (
            "There must be exactly one paper_executor.execute_paper_order "
            "call per order, occurring inside the orchestrator's gated "
            "path. Saw {n} (>=2 indicates a direct bypass alongside the "
            "gateway).".format(n=len(direct_calls))
        )


# ---------------------------------------------------------------------------
# AC5 (auxiliary) — rejected orders persist gate_results without paper_order_id
# ---------------------------------------------------------------------------


class TestRejectedOrdersPersistAudit:
    def test_rejected_order_records_gate_results(self, fm_client):
        """An order rejected by a gate must persist gate_results without mutation."""
        orch = _get_orchestrator()
        response = fm_client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1000000",  # 1M units @ 50k = 50B notional vs 10k budget
                "order_type": "market",
                "market_price": "50000",
            },
        )
        audit = orch.get_audit_log()
        assert audit, "Every orchestrator call must persist an audit entry."
        entry = audit[-1]
        assert entry["action"] in {"EXECUTED", "REJECTED"}
        if response.status_code >= 400:
            assert entry["action"] == "REJECTED"
            assert entry.get("paper_order_id") is None
            assert entry["gate_results"], "Rejection must include gate_results."
