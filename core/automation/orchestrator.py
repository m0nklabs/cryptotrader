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
from typing import Optional, Protocol

from core.automation.audit import AuditEvent, AuditLogger
from core.automation.rules import AutomationConfig, TradeHistory
from core.automation.safety import (
    BalanceCheck,
    CooldownCheck,
    DailyLossCheck,
    DailyTradeCountCheck,
    KillSwitchCheck,
    PositionSizeCheck,
    SafetyCheck,
    SafetyResult,
    run_safety_checks,
)
from core.backtest.strategy import Signal, Strategy
from core.execution.interfaces import OrderExecutor
from core.execution.bitfinex_live import create_bitfinex_live_executor
from core.execution.paper import PaperExecutor
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

    # Trades above this notional require human approval (None disables)
    approval_threshold: Optional[Decimal] = None

    # Stop after N iterations (None = run forever)
    max_iterations: Optional[int] = None


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

    def _build_executor(self) -> OrderExecutor:
        if self.config.dry_run:
            return PaperExecutor()
        if self.config.exchange == "bitfinex":
            return create_bitfinex_live_executor(dry_run=False)
        return PaperExecutor()

    def _build_safety_checks(self, symbol: str) -> list[SafetyCheck]:
        """Build the list of safety checks for a symbol."""
        return [
            KillSwitchCheck(config=self.automation_config),
            PositionSizeCheck(
                config=self.automation_config,
                current_position_value=self.positions.get(symbol, Decimal("0")),
            ),
            CooldownCheck(
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
            ),
            DailyLossCheck(
                config=self.automation_config,
                daily_pnl=self.daily_pnl,
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

            # 4. Build order intent
            intent = OrderIntent(
                exchange=self.config.exchange,
                symbol=symbol,
                side=signal.side,
                amount=self.config.default_position_size / current_price,
                order_type="market",
            )

            # 5. Run safety checks
            safety_checks = self._build_safety_checks(symbol)
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
                notional = self.config.default_position_size
                if notional >= self.config.approval_threshold:
                    reason = f"Trade requires approval: notional {notional} >= {self.config.approval_threshold}"
                    self.audit_logger.log_decision(
                        "approval_required",
                        reason,
                        symbol,
                        context={"amount": str(notional), "threshold": str(self.config.approval_threshold)},
                    )
                    self.audit_logger.log_trade_rejected(symbol, reason, context={"approval_required": True})
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
                self._update_position(symbol, intent)
                self.audit_logger.log_trade_executed(
                    symbol=symbol,
                    side=signal.side,
                    amount=str(intent.amount),
                    context={"dry_run": self.config.dry_run},
                )
                logger.info(f"Trade executed: {signal.side} {intent.amount} {symbol}")
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

    def _update_position(self, symbol: str, intent: OrderIntent) -> None:
        """Update position tracking after a trade."""
        current = self.positions.get(symbol, Decimal("0"))

        if intent.side == "BUY":
            self.positions[symbol] = current + intent.amount
        else:
            self.positions[symbol] = current - intent.amount

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
