"""Strategy Orchestrator - Main trading loop daemon.

This module implements the main trading loop that:
1. Monitors signals from technical indicators
2. Runs safety checks before execution
3. Executes trades via paper or live adapters
4. Logs all decisions for audit

Default behavior is paper-trading (dry_run=True).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Protocol

from core.automation.audit import AuditEvent, AuditLogger
from core.automation.rules import AutomationConfig, TradeHistory
from core.automation.safety import (
    BalanceCheck,
    CooldownCheck,
    DailyLossCheck,
    DailyTradeCountCheck,
    DrawdownCheck,
    KillSwitchCheck,
    PositionSizeCheck,
    SafetyCheck,
    SafetyResult,
    SignalDeduplication,
    run_safety_checks,
)
from core.execution.interfaces import OrderExecutor
from core.execution.bitfinex_live import create_bitfinex_live_executor
from core.execution.paper import PaperExecutor
from core.backtest.strategy import Signal, Strategy
from core.risk.drawdown import DrawdownConfig, DrawdownMonitor
from core.risk.limits import ExposureChecker, ExposureLimits
from core.types import Candle, ExecutionResult, OrderIntent


logger = logging.getLogger(__name__)


class CandleProvider(Protocol):
    """Protocol for fetching latest candles."""

    async def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[Candle]:
        """Fetch the most recent candles for a symbol."""
        ...


class PriceProvider(Protocol):
    """Protocol for getting current market price."""

    async def get_current_price(self, symbol: str) -> Decimal:
        """Get the current market price for a symbol."""
        ...


@dataclass
class TradeDecision:
    """Represents a trading decision from the orchestrator."""

    symbol: str
    signal: Signal
    timestamp: datetime
    safety_result: SafetyResult
    execution_result: Optional[ExecutionResult] = None
    reason: str = ""
    requires_approval: bool = False


@dataclass
class OrchestratorConfig:
    """Configuration for the strategy orchestrator."""

    # Symbols to trade
    symbols: list[str] = field(default_factory=lambda: ["BTCUSD"])

    # Timeframe for signals
    timeframe: str = "1h"

    # Exchange
    exchange: str = "bitfinex"

    # Polling interval in seconds
    poll_interval: int = 60

    # Default position size (in quote currency)
    default_position_size: Decimal = Decimal("100")

    # Paper trading mode (default: True for safety)
    dry_run: bool = True

    # Trades above this notional require human approval (None disables).
    # Approval requests are logged for external handling (no built-in approval flow yet).
    approval_threshold: Decimal | None = None

    # Stop after N iterations (None = run forever)
    max_iterations: Optional[int] = None

    # Drawdown limits (as percentages, e.g., 0.05 = 5%)
    max_daily_drawdown: Decimal | None = None
    max_total_drawdown: Decimal | None = None

    # Exposure limits
    max_position_size_per_symbol: Decimal | None = None
    max_total_exposure: Decimal | None = None
    max_positions: int | None = None


class StrategyOrchestrator:
    """Main trading loop orchestrator.

    Coordinates between:
    - Strategy (generates signals from candles)
    - Safety checks (validates trade is safe)
    - Executor (paper or live order execution)
    - Audit logger (records all decisions)
    """

    def __init__(
        self,
        *,
        config: OrchestratorConfig,
        automation_config: AutomationConfig,
        strategy: Strategy,
        candle_provider: CandleProvider,
        price_provider: PriceProvider,
        executor: Optional[OrderExecutor] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.config = config
        self.automation_config = automation_config
        self.strategy = strategy
        self.candle_provider = candle_provider
        self.price_provider = price_provider
        self.executor = executor or self._build_executor()
        self.audit_logger = audit_logger or AuditLogger()

        # State
        self.trade_history = TradeHistory()
        self.positions: dict[str, Decimal] = {}  # symbol -> position size
        self.daily_pnl: Decimal = Decimal("0")
        self.current_balance: Decimal = Decimal("10000")  # Initial balance
        self._running = False
        self._iteration = 0

        # Drawdown monitoring
        self.drawdown_monitor = DrawdownMonitor(
            config=DrawdownConfig(
                max_daily_drawdown=config.max_daily_drawdown,
                max_total_drawdown=config.max_total_drawdown,
            ),
        )
        # Initialize with starting balance
        self.drawdown_monitor.update_balance(self.current_balance)

        # Exposure checking
        self.exposure_checker = ExposureChecker(
            limits=ExposureLimits(
                max_position_size_per_symbol=config.max_position_size_per_symbol,
                max_total_exposure=config.max_total_exposure,
                max_positions=config.max_positions,
            ),
        )

    def _build_executor(self) -> OrderExecutor:
        if self.config.dry_run:
            logger.info("Initializing paper executor (dry_run=True).")
            return PaperExecutor()
        if self.config.exchange == "bitfinex":
            logger.warning(
                "Initializing Bitfinex executor for live trading (dry_run=False). "
                "Valid Bitfinex API credentials must be configured."
            )
            return create_bitfinex_live_executor(dry_run=False)
        logger.warning(
            "Live trading requested (dry_run=%s) for unsupported exchange '%s'. Falling back to PaperExecutor.",
            self.config.dry_run,
            self.config.exchange,
        )
        return PaperExecutor()

    def _build_safety_checks(self, symbol: str, current_price: Decimal = Decimal("1")) -> list[SafetyCheck]:
        """Build the list of safety checks for a symbol."""
        # Update drawdown with current balance
        self.drawdown_monitor.update_balance(self.current_balance)

        return [
            KillSwitchCheck(config=self.automation_config),
            PositionSizeCheck(
                config=self.automation_config,
                current_position_value=self.positions.get(symbol, Decimal("0")),
                current_price=current_price,
            ),
            CooldownCheck(
                config=self.automation_config,
                trade_history=self.trade_history,
            ),
            SignalDeduplication(
                config=self.automation_config,
                trade_history=self.trade_history,
            ),
            DailyTradeCountCheck(
                config=self.automation_config,
                trade_history=self.trade_history,
            ),
            BalanceCheck(
                config=self.automation_config,
                current_balance=self.current_balance,
                current_price=current_price,
            ),
            DailyLossCheck(
                config=self.automation_config,
                daily_pnl=self.daily_pnl,
            ),
            DrawdownCheck(
                trading_paused=self.drawdown_monitor.state.trading_paused,
                daily_drawdown_pct=self.drawdown_monitor.get_daily_drawdown(),
                total_drawdown_pct=self.drawdown_monitor.get_total_drawdown(),
                max_daily_drawdown=self.config.max_daily_drawdown,
                max_total_drawdown=self.config.max_total_drawdown,
            ),
        ]

    async def _process_symbol(self, symbol: str) -> Optional[TradeDecision]:
        """Process a single symbol and potentially execute a trade."""
        try:
            # 1. Fetch latest candles
            candles = await self.candle_provider.get_latest_candles(
                symbol=symbol,
                timeframe=self.config.timeframe,
                limit=100,
            )

            if len(candles) < 15:
                logger.warning(f"Not enough candles for {symbol}: {len(candles)} < 15")
                return None

            # 2. Calculate indicators and get signal
            # Pass last candle and full history for indicator calculation
            indicators = self._calculate_indicators(candles)
            signal = self.strategy.on_candle(candles[-1], indicators)

            if signal is None or signal.side == "HOLD":
                logger.debug(f"No trade signal for {symbol}")
                return None

            logger.info(f"Signal for {symbol}: {signal.side} (strength={signal.strength})")

            # 3. Get current price
            current_price = await self.price_provider.get_current_price(symbol)

            # 4. Build order intent. For paper trading we attach the
            #    authoritative market price + timestamp under ``extra`` so
            #    PaperExecutor.execute() can route through execute_paper_order()
            #    instead of returning the legacy dry-run stub.
            price_update_time = datetime.now(timezone.utc)
            intent = OrderIntent(
                exchange=self.config.exchange,
                symbol=symbol,
                side=signal.side,
                amount=self.config.default_position_size / current_price,
                order_type="market",
                extra={
                    "market_price": current_price,
                    "price_update_time": price_update_time,
                },
            )

            # 5. Run safety checks
            safety_checks = self._build_safety_checks(symbol, current_price=current_price)
            safety_result = run_safety_checks(checks=safety_checks, intent=intent)

            if not safety_result.ok:
                logger.warning(f"Safety check failed for {symbol}: {safety_result.reason}")
                self.audit_logger.log_trade_rejected(symbol, safety_result.reason)
                return TradeDecision(
                    symbol=symbol,
                    signal=signal,
                    timestamp=datetime.now(timezone.utc),
                    safety_result=safety_result,
                    reason=f"Safety check failed: {safety_result.reason}",
                )

            # 5b. Human approval gate for large trades
            if self.config.approval_threshold is not None:
                notional = intent.amount * current_price
                if notional >= self.config.approval_threshold:
                    reason = f"Trade requires approval: notional {notional} >= {self.config.approval_threshold}"
                    approval_context = {
                        "amount": str(notional),
                        "threshold": str(self.config.approval_threshold),
                    }
                    self.audit_logger.log_decision("approval_required", reason, symbol, context=approval_context)
                    self.audit_logger.log_trade_deferred(symbol, reason, context=approval_context)
                    return TradeDecision(
                        symbol=symbol,
                        signal=signal,
                        timestamp=datetime.now(timezone.utc),
                        safety_result=safety_result,
                        reason=reason,
                        requires_approval=True,
                    )

            # 6. Execute order
            if self.config.dry_run:
                logger.info(f"DRY RUN: Would execute {signal.side} {intent.amount} {symbol}")

            execution_result = self.executor.execute(intent)

            # 7. Update state
            if execution_result.accepted:
                self.trade_history.add_trade(symbol, datetime.now(timezone.utc))

                # For paper trading the position must be derived from the
                # authoritative PaperExecutor ledger (recorded fills), not from
                # the requested intent. This avoids double-tracking and prevents
                # automation results from diverging from the API paper ledger.
                if isinstance(self.executor, PaperExecutor):
                    self._sync_position_from_paper(symbol)
                else:
                    self._update_position(symbol, intent, price=current_price)

                # Update drawdown with new balance
                self.drawdown_monitor.update_balance(self.current_balance)

                # Log trade with rich context if PaperExecutor
                audit_context: dict[str, Any] = {"dry_run": self.config.dry_run}
                fill_price: Decimal | None = None
                fees: Decimal | None = None
                slippage_bps: int | None = None
                fill_status: str | None = None
                paper_order_id: str | None = None

                if isinstance(self.executor, PaperExecutor):
                    fees = self.executor.get_fees_by_symbol(symbol)
                    audit_context["fees_this_symbol"] = str(fees)
                    audit_context["total_fees"] = str(self.executor.get_total_fees())
                    audit_context["fee_model"] = {
                        "maker": str(self.executor.get_fee_model().breakdown.maker_fee_rate),
                        "taker": str(self.executor.get_fee_model().breakdown.taker_fee_rate),
                    }
                    # Pull fill metadata off the durable PaperOrder ledger so
                    # the audit event carries the same facts the API layer
                    # sees (issue #428 acceptance criteria).
                    paper_order = self._latest_paper_order_for_symbol(symbol)
                    if paper_order is not None:
                        audit_context["order_id"] = str(paper_order.order_id)
                        audit_context["symbol"] = paper_order.symbol
                        paper_order_id = str(paper_order.order_id)
                        fill_price = paper_order.fill_price
                        fees = paper_order.fees if paper_order.fees is not None else fees
                        slippage_bps = (
                            int(paper_order.slippage_bps)
                            if paper_order.slippage_bps is not None
                            else None
                        )
                        fill_status = paper_order.status

                self.audit_logger.log_trade_executed(
                    symbol=symbol,
                    side=signal.side,
                    amount=str(intent.amount),
                    context=audit_context,
                    fill_price=fill_price,
                    fees=fees,
                    slippage_bps=slippage_bps,
                    fill_status=fill_status,
                )
                logger.info(
                    "Trade executed: %s %s %s (order_id=%s, fill_status=%s, fill_price=%s)",
                    signal.side,
                    intent.amount,
                    symbol,
                    paper_order_id or "n/a",
                    fill_status or "n/a",
                    fill_price if fill_price is not None else "n/a",
                )
            else:
                logger.error(f"Trade rejected by executor: {execution_result.reason}")
                self.audit_logger.log_trade_rejected(symbol, execution_result.reason)

            return TradeDecision(
                symbol=symbol,
                signal=signal,
                timestamp=datetime.now(timezone.utc),
                safety_result=safety_result,
                execution_result=execution_result,
            )

        except Exception as e:
            logger.exception(f"Error processing {symbol}: {e}")
            self.audit_logger.log(
                AuditEvent(
                    event_type="error",
                    message=f"Error processing {symbol}: {e}",
                    severity="error",
                )
            )
            return None

    def _calculate_indicators(self, candles: list[Candle]) -> dict:
        """Calculate indicators from candles for strategy use."""
        from core.indicators.rsi import compute_rsi

        indicators = {}

        if len(candles) >= 14:
            indicators["rsi"] = compute_rsi(candles, period=14)

        return indicators

    def _update_position(
        self,
        symbol: str,
        intent: OrderIntent,
        price: Decimal = Decimal("1"),
    ) -> None:
        """Update position tracking after a trade.

        Stores market value (amount * price) in quote currency,
        so position limits compare apples-to-apples with
        max_position_size which is denominated in quote currency.
        """
        current = self.positions.get(symbol, Decimal("0"))
        market_value = intent.amount * price

        if intent.side == "BUY":
            self.positions[symbol] = current + market_value
        else:
            self.positions[symbol] = current - market_value

    def _sync_position_from_paper(self, symbol: str) -> None:
        """Mirror the PaperExecutor ledger into self.positions.

        Replaces the legacy intent-driven _update_position() for paper runs
        so that risk/limit state and audit reconciliation reflect recorded
        fills, not the requested intent. If the paper ledger has no position
        for ``symbol`` (e.g. the fill missed), the orchestrator-side entry
        is removed.
        """
        assert isinstance(self.executor, PaperExecutor), "expected PaperExecutor"
        paper_position = self.executor.get_position(symbol)
        if paper_position is None or paper_position.qty == 0:
            self.positions.pop(symbol, None)
            return
        # Mirror in quote-currency market value so position-limit checks
        # (which compare against max_position_size in quote currency)
        # remain apples-to-apples with the legacy intent math.
        self.positions[symbol] = paper_position.qty * paper_position.avg_entry

    def _latest_paper_order_for_symbol(self, symbol: str):
        """Return the most recent PaperOrder for ``symbol`` from the ledger,
        or None if the executor is not a PaperExecutor / no order recorded."""
        if not isinstance(self.executor, PaperExecutor):
            return None
        orders = self.executor.get_orders_by_symbol(symbol)
        if not orders:
            return None
        # PaperOrder.order_id is monotonically increasing per executor instance,
        # so the highest id corresponds to the most recent order.
        return max(orders, key=lambda o: o.order_id)

    async def run_once(self) -> list[TradeDecision]:
        """Run one iteration of the trading loop."""
        self._iteration += 1
        logger.info(f"=== Orchestrator iteration {self._iteration} ===")

        decisions = []
        for symbol in self.config.symbols:
            decision = await self._process_symbol(symbol)
            if decision:
                decisions.append(decision)

        return decisions

    async def run(self) -> None:
        """Run the main trading loop."""
        logger.info("Starting Strategy Orchestrator")
        logger.info(f"Config: symbols={self.config.symbols}, timeframe={self.config.timeframe}")
        logger.info(f"Mode: {'PAPER TRADING' if self.config.dry_run else '🔴 LIVE TRADING 🔴'}")

        self._running = True

        try:
            while self._running:
                await self.run_once()

                # Check iteration limit
                if self.config.max_iterations and self._iteration >= self.config.max_iterations:
                    logger.info(f"Reached max iterations ({self.config.max_iterations})")
                    break

                # Wait for next iteration
                logger.debug(f"Sleeping {self.config.poll_interval}s until next iteration")
                await asyncio.sleep(self.config.poll_interval)

        except asyncio.CancelledError:
            logger.info("Orchestrator cancelled")
        finally:
            self._running = False
            logger.info("Orchestrator stopped")

    def stop(self) -> None:
        """Signal the orchestrator to stop."""
        self._running = False


# ========== Concrete Implementations ==========


class BitfinexCandleProvider:
    """Fetch candles from Bitfinex via REST API."""

    def __init__(self, client=None):
        # Lazy import to avoid circular dependencies
        if client is None:
            from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient

            client = BitfinexClient()
        self.client = client

    async def get_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[Candle]:
        """Fetch candles from Bitfinex."""
        # Bitfinex API is sync, wrap in executor
        import asyncio

        loop = asyncio.get_event_loop()
        candles_data = await loop.run_in_executor(
            None,
            lambda: self.client.get_candles(
                timeframe=timeframe,
                symbol=f"t{symbol}",
                limit=limit,
                sort=-1,  # newest first from API
            ),
        )

        # Reverse to get chronological order (oldest to newest)
        candles_data.reverse()

        return [
            Candle(
                exchange="bitfinex",
                symbol=symbol,
                timeframe=timeframe,
                open_time=datetime.fromtimestamp(c["timestamp"] / 1000, tz=timezone.utc),
                close_time=datetime.fromtimestamp(c["timestamp"] / 1000, tz=timezone.utc),
                open=Decimal(str(c["open"])),
                high=Decimal(str(c["high"])),
                low=Decimal(str(c["low"])),
                close=Decimal(str(c["close"])),
                volume=Decimal(str(c["volume"])),
            )
            for c in candles_data
        ]


class BitfinexPriceProvider:
    """Get current price from Bitfinex."""

    def __init__(self, client=None):
        if client is None:
            from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient

            client = BitfinexClient()
        self.client = client

    async def get_current_price(self, symbol: str) -> Decimal:
        """Get last traded price from Bitfinex."""
        import asyncio

        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(
            None,
            lambda: self.client.get_ticker(f"t{symbol}"),
        )

        return Decimal(str(ticker.get("last_price", 0)))


# ========== CLI Entry Point ==========


async def main():
    """Run the orchestrator from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the trading orchestrator")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD"], help="Symbols to trade")
    parser.add_argument("--timeframe", default="1h", help="Timeframe (default: 1h)")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
    parser.add_argument("--position-size", type=float, default=100, help="Position size in USD")
    parser.add_argument("--live", action="store_true", help="Enable live trading (default: paper)")
    parser.add_argument("--iterations", type=int, help="Max iterations (default: infinite)")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Build config
    config = OrchestratorConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        poll_interval=args.interval,
        default_position_size=Decimal(str(args.position_size)),
        dry_run=not args.live,
        max_iterations=args.iterations,
    )

    # Build automation config (enable automation)
    automation_config = AutomationConfig(
        enabled=True,
        max_daily_trades_global=50,
        cooldown_seconds_default=60,
    )

    # Build strategy
    from core.backtest.engine import RSIStrategy

    strategy = RSIStrategy(oversold=30.0, overbought=70.0)

    # Build providers
    candle_provider = BitfinexCandleProvider()
    price_provider = BitfinexPriceProvider()

    # Build orchestrator
    orchestrator = StrategyOrchestrator(
        config=config,
        automation_config=automation_config,
        strategy=strategy,
        candle_provider=candle_provider,
        price_provider=price_provider,
    )

    # Run
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
