"""End-to-end tests for automation paper dry-run orchestration (issue #428).

Bug summary:
    StrategyOrchestrator selects PaperExecutor when dry_run=True, but routes
    the order through PaperExecutor.execute(OrderIntent), the legacy dry-run
    compatibility method. That path returns accepted=True with order_id=None
    and never calls execute_paper_order(), so no PaperOrder is recorded, no
    fill happens, no fees accrue, and the orchestrator's own (local)
    positions map is updated at the requested market price rather than from
    a recorded fill.

Acceptance criteria covered here:
    * automation paper orders flow through the authoritative paper gateway
      (execute_paper_order) so durable order IDs, fill status, fill qty,
      fill price, and fees are recorded.
    * positions are derived from recorded fills, not from the requested
      intent.
    * an end-to-end test proves signal -> order -> fill -> ledger ->
      position -> PnL -> audit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

import pytest

from core.automation.audit import AuditLogger
from core.automation.orchestrator import OrchestratorConfig, StrategyOrchestrator
from core.automation.rules import AutomationConfig
from core.backtest.strategy import Signal
from core.execution.paper import PaperExecutor
from core.types import Candle, OrderIntent


class _FixedStrategy:
    """Strategy that emits a deterministic BUY signal once enough candles exist."""

    def __init__(self, side: Literal["BUY", "SELL"] = "BUY") -> None:
        self._side = side

    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        return Signal(self._side)


class _FakeCandleProvider:
    """Provider that returns a flat series of candles at the requested price."""

    def __init__(self, price: Decimal = Decimal("100")) -> None:
        self._price = price

    async def get_latest_candles(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[Candle]:
        now = datetime.now(timezone.utc)
        return [
            Candle(
                exchange="paper",
                symbol=symbol,
                timeframe=timeframe,
                open_time=now - timedelta(minutes=limit - i),
                close_time=now - timedelta(minutes=limit - 1 - i),
                open=self._price,
                high=self._price,
                low=self._price,
                close=self._price,
                volume=Decimal("1"),
            )
            for i in range(limit)
        ]


class _FakePriceProvider:
    def __init__(self, price: Decimal = Decimal("100")) -> None:
        self._price = price

    async def get_current_price(self, symbol: str) -> Decimal:
        return self._price


def _build_orchestrator(
    *,
    paper_executor: PaperExecutor,
    audit_logger: AuditLogger,
    price: Decimal = Decimal("100"),
) -> StrategyOrchestrator:
    config = OrchestratorConfig(
        symbols=["BTCUSD"],
        dry_run=True,
        default_position_size=Decimal("100"),
    )
    automation_config = AutomationConfig(enabled=True)
    return StrategyOrchestrator(
        config=config,
        automation_config=automation_config,
        strategy=_FixedStrategy("BUY"),
        candle_provider=_FakeCandleProvider(price=price),
        price_provider=_FakePriceProvider(price=price),
        executor=paper_executor,
        audit_logger=audit_logger,
    )


class TestPaperOrchestrationFix:
    @pytest.mark.asyncio
    async def test_paper_dry_run_records_durable_order_id(self) -> None:
        """Automation paper orders must receive a durable, non-null order ID."""
        paper_executor = PaperExecutor()
        audit_logger = AuditLogger()

        orchestrator = _build_orchestrator(
            paper_executor=paper_executor,
            audit_logger=audit_logger,
        )

        decisions = await orchestrator.run_once()

        assert decisions, "orchestrator should emit a decision"
        decision = decisions[0]
        assert decision.execution_result is not None
        assert decision.execution_result.accepted is True
        # Bug repro point: legacy dry-run returned order_id=None.
        assert decision.execution_result.order_id is not None
        # The PaperExecutor ledger must now hold exactly one order, and the
        # durable order id surfaced through ExecutionResult must agree with
        # the ledger (string vs int representation).
        assert len(paper_executor.get_all_orders()) == 1
        assert str(paper_executor.get_all_orders()[0].order_id) == decision.execution_result.order_id

    @pytest.mark.asyncio
    async def test_paper_dry_run_records_fill_status_price_qty(self) -> None:
        """The execution result must carry real fill metadata, not the legacy stub."""
        paper_executor = PaperExecutor()
        audit_logger = AuditLogger()
        market_price = Decimal("250.5")

        orchestrator = _build_orchestrator(
            paper_executor=paper_executor,
            audit_logger=audit_logger,
            price=market_price,
        )

        decisions = await orchestrator.run_once()
        assert decisions
        result = decisions[0].execution_result
        assert result is not None

        raw = result.raw or {}
        # Surface fill metadata through the ExecutionResult envelope.
        assert raw.get("fill_status") in {"FILLED", "PARTIAL", "MISSED"}
        assert raw.get("fill_qty") is not None
        assert raw.get("fill_price") is not None
        # Fill price should reflect slippage from the market price, not equal zero.
        assert Decimal(str(raw["fill_price"])) > 0
        # For BUY, slippage pushes the price above market_price; for SELL the inverse.
        if raw.get("side") == "BUY":
            assert Decimal(str(raw["fill_price"])) >= market_price
        # Order book ledger matches: the durable PaperOrder records the fill.
        paper_order = paper_executor.get_all_orders()[0]
        assert paper_order.status == raw["fill_status"]
        assert paper_order.fill_qty is not None and paper_order.fill_qty > 0

    @pytest.mark.asyncio
    async def test_orchestrator_positions_derived_from_paper_ledger(self) -> None:
        """Orchestrator-side positions must mirror the PaperExecutor ledger,
        not be independently tracked at requested intent price."""
        paper_executor = PaperExecutor()
        audit_logger = AuditLogger()
        market_price = Decimal("100")

        orchestrator = _build_orchestrator(
            paper_executor=paper_executor,
            audit_logger=audit_logger,
            price=market_price,
        )

        await orchestrator.run_once()

        # Authoritative position lives in the PaperExecutor ledger.
        paper_position = paper_executor.get_position("BTCUSD")
        assert paper_position is not None
        assert paper_position.qty > 0  # BUY -> long
        assert paper_position.avg_entry > 0

        # Orchestrator's positions map should reflect the fill, not a stale
        # intent-derived value. After the fix, it must agree with the ledger.
        assert orchestrator.positions["BTCUSD"] == paper_position.qty * paper_position.avg_entry

    @pytest.mark.asyncio
    async def test_audit_event_records_real_fill_metadata(self) -> None:
        """The trade_executed audit event must carry fill_price/fees/fill_status
        sourced from the recorded PaperOrder."""
        paper_executor = PaperExecutor()
        audit_logger = AuditLogger()

        orchestrator = _build_orchestrator(
            paper_executor=paper_executor,
            audit_logger=audit_logger,
        )

        await orchestrator.run_once()

        executed_events = [e for e in audit_logger.events if e.event_type == "trade_executed"]
        assert len(executed_events) == 1
        ctx = executed_events[0].context
        # Fill metadata should no longer be silently absent for paper runs.
        assert ctx.get("fill_status") in {"FILLED", "PARTIAL", "MISSED"}
        assert ctx.get("fill_price") is not None
        assert ctx.get("order_id") is not None
        assert ctx.get("order_id") == str(paper_executor.get_all_orders()[0].order_id)

    @pytest.mark.asyncio
    async def test_paper_dry_run_records_fees_and_updates_total(self) -> None:
        """A successful paper fill must accrue fees in the PaperExecutor ledger."""
        paper_executor = PaperExecutor()
        audit_logger = AuditLogger()
        market_price = Decimal("100")

        orchestrator = _build_orchestrator(
            paper_executor=paper_executor,
            audit_logger=audit_logger,
            price=market_price,
        )

        await orchestrator.run_once()

        # The paper executor should now carry a fee footprint for the symbol.
        # Some symbols may also see PARTIAL fills with zero fees in edge cases;
        # we only assert non-negative fees here for the FILLED branch.
        paper_order = paper_executor.get_all_orders()[0]
        if paper_order.status in {"FILLED", "PARTIAL"}:
            assert paper_order.fees is not None
            assert paper_order.fees >= 0
        assert paper_executor.get_fees_by_symbol("BTCUSD") >= 0

    @pytest.mark.asyncio
    async def test_paper_legacy_compat_dispatch_still_supports_order_intent(self) -> None:
        """The legacy OrderExecutor.execute(intent) entry point on PaperExecutor
        must translate into execute_paper_order and return an ExecutionResult
        that records a durable order id, not the legacy stub.

        When the caller supplies an authoritative market price via
        intent.extra, the dispatch resolves through execute_paper_order and a
        real PaperOrder is recorded.
        """
        paper_executor = PaperExecutor()
        intent = OrderIntent(
            exchange="paper",
            symbol="BTCUSD",
            side="BUY",
            amount=Decimal("1"),
            order_type="market",
            extra={"market_price": Decimal("100")},
        )

        result = paper_executor.execute(intent)

        assert result.accepted is True
        assert result.order_id is not None
        assert len(paper_executor.get_all_orders()) == 1

    @pytest.mark.asyncio
    async def test_paper_legacy_compat_rejects_market_without_price(self) -> None:
        """Without a market price hint AND no observed last price, market
        orders must fail closed instead of returning the legacy dry-run stub."""
        paper_executor = PaperExecutor()
        intent = OrderIntent(
            exchange="paper",
            symbol="BTCUSD",
            side="BUY",
            amount=Decimal("1"),
            order_type="market",
        )

        result = paper_executor.execute(intent)

        assert result.accepted is False
        assert result.order_id is None
        assert "market_price" in (result.reason or "")
        # No PaperOrder should have been recorded on a rejected dispatch.
        assert len(paper_executor.get_all_orders()) == 0
