"""Position sizing algorithms for risk management.

Implements various position sizing methods:
- Fixed fractional: risk X% of portfolio per trade
- Kelly criterion: optimal sizing based on win rate
- ATR-based sizing: adjust for volatility
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass
class PositionSize:
    """Position sizing configuration.

    Attributes:
        method: Sizing method ('fixed', 'kelly', 'atr')
        portfolio_percent: Percentage of portfolio to risk (for 'fixed' method)
        kelly_fraction: Fraction of Kelly criterion to use (for 'kelly' method)
        win_rate: Historical win rate (for 'kelly' method)
        avg_win: Average win amount (for 'kelly' method)
        avg_loss: Average loss amount (for 'kelly' method)
        atr_multiplier: ATR multiplier for position sizing (for 'atr' method)
    """

    method: Literal["fixed", "kelly", "atr"]
    portfolio_percent: Decimal | None = None
    kelly_fraction: Decimal | None = None
    win_rate: Decimal | None = None
    avg_win: Decimal | None = None
    avg_loss: Decimal | None = None
    atr_multiplier: Decimal | None = None


def calculate_position_size(
    config: PositionSize,
    portfolio_value: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
    atr: Decimal | None = None,
) -> Decimal:
    """Calculate position size based on configured method.

    Args:
        config: Position sizing configuration
        portfolio_value: Total portfolio value
        entry_price: Entry price for the position
        stop_loss_price: Stop loss price
        atr: Average True Range (required for 'atr' method)

    Returns:
        Position size in number of units

    Raises:
        ValueError: If required parameters are missing or invalid
    """
    if config.method == "fixed":
        return _calculate_fixed_fractional(config, portfolio_value, entry_price, stop_loss_price)
    elif config.method == "kelly":
        return _calculate_kelly(config, portfolio_value, entry_price, stop_loss_price)
    elif config.method == "atr":
        if atr is None:
            raise ValueError("ATR is required for 'atr' method")
        return _calculate_atr_based(config, portfolio_value, entry_price, atr)
    else:
        raise ValueError(f"Unknown sizing method: {config.method}")


def _calculate_fixed_fractional(
    config: PositionSize,
    portfolio_value: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
) -> Decimal:
    """Calculate position size using fixed fractional method.

    Risk a fixed percentage of portfolio value per trade.

    Args:
        config: Position sizing configuration
        portfolio_value: Total portfolio value
        entry_price: Entry price for the position
        stop_loss_price: Stop loss price

    Returns:
        Position size in number of units
    """
    if config.portfolio_percent is None:
        raise ValueError("portfolio_percent is required for 'fixed' method")

    # Calculate risk amount
    risk_amount = portfolio_value * config.portfolio_percent

    # Calculate risk per unit
    risk_per_unit = abs(entry_price - stop_loss_price)

    if risk_per_unit == 0:
        raise ValueError("Risk per unit cannot be zero (entry_price == stop_loss_price)")

    # Calculate position size
    position_size = risk_amount / risk_per_unit

    return position_size


def _calculate_kelly(
    config: PositionSize,
    portfolio_value: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
) -> Decimal:
    """Calculate position size using Kelly criterion.

    Optimal sizing based on win rate and risk/reward ratio.

    Args:
        config: Position sizing configuration
        portfolio_value: Total portfolio value
        entry_price: Entry price for the position
        stop_loss_price: Stop loss price

    Returns:
        Position size in number of units
    """
    if config.win_rate is None or config.avg_win is None or config.avg_loss is None:
        raise ValueError("win_rate, avg_win, and avg_loss are required for 'kelly' method")

    if config.kelly_fraction is None:
        config.kelly_fraction = Decimal("1.0")  # Full Kelly by default

    # Kelly formula: f* = (p * b - q) / b
    # where p = win rate, q = loss rate, b = avg_win / avg_loss
    p = config.win_rate
    q = Decimal("1") - p
    b = config.avg_win / config.avg_loss if config.avg_loss > 0 else Decimal("0")

    kelly_percent = (p * b - q) / b if b > 0 else Decimal("0")

    # Apply fraction of Kelly
    fractional_kelly = kelly_percent * config.kelly_fraction

    # Ensure non-negative
    fractional_kelly = max(fractional_kelly, Decimal("0"))

    # Calculate risk amount
    risk_amount = portfolio_value * fractional_kelly

    # Calculate risk per unit
    risk_per_unit = abs(entry_price - stop_loss_price)

    if risk_per_unit == 0:
        raise ValueError("Risk per unit cannot be zero (entry_price == stop_loss_price)")

    # Calculate position size
    position_size = risk_amount / risk_per_unit

    return position_size


def _calculate_atr_based(
    config: PositionSize,
    portfolio_value: Decimal,
    entry_price: Decimal,
    atr: Decimal,
) -> Decimal:
    """Calculate position size based on ATR (volatility-adjusted).

    Args:
        config: Position sizing configuration
        portfolio_value: Total portfolio value
        entry_price: Entry price for the position
        atr: Average True Range

    Returns:
        Position size in number of units
    """
    if config.atr_multiplier is None:
        raise ValueError("atr_multiplier is required for 'atr' method")

    # Calculate risk amount based on ATR
    risk_amount = portfolio_value * config.atr_multiplier

    # Use ATR as the risk per unit
    if atr == 0:
        raise ValueError("ATR cannot be zero")

    # Calculate position size
    position_size = risk_amount / atr

    return position_size
