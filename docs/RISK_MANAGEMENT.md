# Risk Management Module

The risk management module provides tools for controlling trading risk through position sizing, exposure limits, and drawdown monitoring.

## Components

### Position Sizing (`core/risk/sizing.py`)

Calculate appropriate position sizes based on risk parameters.

**Supported Methods:**

1. **Fixed Fractional** - Risk a fixed percentage of portfolio per trade
2. **Kelly Criterion** - Optimal sizing based on win rate and risk/reward
3. **ATR-Based** - Volatility-adjusted sizing using Average True Range

**Example:**

```python
from core.risk import PositionSize, calculate_position_size
from decimal import Decimal

# Fixed fractional: risk 1% of portfolio
config = PositionSize(method="fixed", portfolio_percent=Decimal("0.01"))
size = calculate_position_size(
    config=config,
    portfolio_value=Decimal("10000"),  # $10,000 portfolio
    entry_price=Decimal("100"),        # Entry at $100
    stop_loss_price=Decimal("99")      # Stop at $99
)
# Result: 100 units (risk $100 / $1 per unit)
```

### Exposure Limits (`core/risk/limits.py`)

Enforce position size and portfolio-wide exposure limits.

**Features:**
- Max position size per symbol
- Max total portfolio exposure
- Max number of open positions

**Example:**

```python
from core.risk import ExposureLimits, ExposureChecker
from decimal import Decimal

limits = ExposureLimits(
    max_position_size_per_symbol=Decimal("5000"),
    max_total_exposure=Decimal("0.95"),  # 95% max
    max_positions=10
)

checker = ExposureChecker(limits)

# Check if new position is allowed
allowed, reasons = checker.check_all(
    symbol="BTC/USD",
    position_value=Decimal("3000"),
    current_exposure=Decimal("5000"),
    portfolio_value=Decimal("10000"),
    current_positions=5
)

if not allowed:
    print(f"Order rejected: {reasons}")
```

### Drawdown Controls (`core/risk/drawdown.py`)

Monitor portfolio drawdown and pause trading when limits are exceeded.

**Features:**
- Daily drawdown tracking (resets each day)
- Total drawdown tracking (since inception)
- Automatic trading pause when limits exceeded
- Kill switch for severe drawdowns

**Example:**

```python
from core.risk import DrawdownConfig, DrawdownMonitor
from decimal import Decimal

# Configure limits
config = DrawdownConfig(
    max_daily_drawdown=Decimal("0.05"),   # 5% daily max
    max_total_drawdown=Decimal("0.20")    # 20% total max
)

monitor = DrawdownMonitor(config)

# Update with current balance
monitor.update_balance(Decimal("1000"))

# Check if trading is allowed
if monitor.is_trading_allowed():
    # Execute trades
    pass
else:
    print("Trading paused due to drawdown")

# Get current drawdown metrics
daily_dd = monitor.get_daily_drawdown()
total_dd = monitor.get_total_drawdown()
```

## Integration

Risk checks should run **before every order**:

1. Calculate position size based on risk parameters
2. Check exposure limits
3. Verify drawdown limits
4. Log any violations

**Example Integration:**

```python
from core.risk import (
    PositionSize, calculate_position_size,
    ExposureChecker, ExposureLimits,
    DrawdownMonitor, DrawdownConfig
)
from decimal import Decimal

def execute_order(symbol, entry_price, stop_loss_price):
    # 1. Check drawdown
    if not drawdown_monitor.is_trading_allowed():
        return {"status": "rejected", "reason": "Trading paused due to drawdown"}

    # 2. Calculate position size
    position_size = calculate_position_size(
        sizing_config,
        portfolio_value,
        entry_price,
        stop_loss_price
    )

    # 3. Check exposure limits
    position_value = position_size * entry_price
    allowed, reasons = exposure_checker.check_all(
        symbol=symbol,
        position_value=position_value,
        current_exposure=get_current_exposure(),
        portfolio_value=portfolio_value,
        current_positions=get_position_count()
    )

    if not allowed:
        return {"status": "rejected", "reason": reasons}

    # 4. Execute order
    return execute_trade(symbol, position_size)
```

## Configuration

Risk parameters can be configured via:
- Environment variables
- Database settings
- Configuration files

**Example `.env` configuration:**

```bash
# Position sizing
RISK_METHOD=fixed
RISK_PORTFOLIO_PERCENT=0.01

# Exposure limits
RISK_MAX_POSITION_SIZE=5000
RISK_MAX_TOTAL_EXPOSURE=0.95
RISK_MAX_POSITIONS=10

# Drawdown controls
RISK_MAX_DAILY_DRAWDOWN=0.05
RISK_MAX_TOTAL_DRAWDOWN=0.20
```

## Logging

All risk violations should be logged for audit purposes:

```python
import logging

logger = logging.getLogger(__name__)

if not allowed:
    logger.warning(
        "Order rejected due to risk limits",
        extra={
            "symbol": symbol,
            "reasons": reasons,
            "position_value": position_value,
            "current_exposure": current_exposure
        }
    )
```

## Testing

Comprehensive tests are available in `tests/test_risk.py`:

```bash
# Run risk tests
pytest tests/test_risk.py -v

# Run with coverage
pytest tests/test_risk.py --cov=core/risk --cov-report=term-missing
```

## Boundary Conditions

**Important:** When drawdown equals the configured limit, it is considered **within limits** (not exceeded):
- At exactly 5% drawdown with 5% limit → Trading allowed
- Over 5% drawdown with 5% limit → Trading paused

This provides a clear, conservative boundary for risk management.
