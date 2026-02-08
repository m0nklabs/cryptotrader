# AI Agent Role Implementations

This document describes the implementation details of the four agent roles in the Multi-Brain AI system.

## Overview

The Multi-Brain AI system uses four specialized agent roles that work together to make trading decisions:

1. **Screener** - High-throughput bulk filtering
2. **Tactical** - Technical analysis and price action
3. **Fundamental** - News, sentiment, and macro analysis
4. **Strategist** - Portfolio risk management and veto power

Each role is implemented as a subclass of `AgentRole` and follows a consistent pattern:
- `build_prompt()` - Enriches the user prompt with role-specific context
- `parse_response()` - Parses LLM output into a structured `RoleVerdict`
- `evaluate()` - Orchestrates the full evaluation pipeline

## Screener Role

**Purpose**: Quickly scan many symbols and discard obvious no-trades before expensive LLM analysis.

**Default Provider**: DeepSeek V3.2 (cheapest, fast)

### Key Features

#### Quick-Reject Heuristics
Pre-filters symbols before LLM calls to save costs:
- **Low volume**: < $100k daily volume → reject
- **Extreme RSI**: > 95 (overbought) or < 5 (oversold) → reject
- **Tight Bollinger Bands**: < 1% width (low volatility) → reject

#### Batch Processing
- Accepts list of symbols with their indicator snapshots
- Applies quick-reject to each symbol
- Passes only filtered symbols to LLM
- Returns both passed and rejected symbols with reasons

#### Indicator Injection
Serializes indicator snapshots for each symbol:
- RSI, MACD, volume, Bollinger Bands
- ATR, Stochastic (if provided)
- Custom indicators via `serialize_indicators()`

### Example Usage

```python
from core.ai.roles.screener import ScreenerRole
from core.ai.types import AIRequest, RoleName

screener = ScreenerRole()
request = AIRequest(
    role=RoleName.SCREENER,
    user_prompt="Find trading opportunities",
    context={
        "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
        "timeframe": "1h",
        "indicators": {
            "BTC/USD": {"volume_24h": 1000000, "rsi": 55, "bb_upper": 51000, "bb_lower": 49000, "bb_middle": 50000},
            "ETH/USD": {"volume_24h": 500000, "rsi": 60},
            "SOL/USD": {"volume_24h": 50000, "rsi": 45}  # Will be filtered (low volume)
        }
    }
)

# In a real scenario, this would call the LLM provider
# prompt = screener.build_prompt(request)
# response = await provider.complete(request, system_prompt, ...)
# verdict = screener.parse_response(response)
```

### Output Format

```json
{
  "action": "BUY",
  "confidence": 0.75,
  "reasoning": "Found 2 strong opportunities",
  "passed_symbols": ["BTC/USD", "ETH/USD"],
  "skipped_symbols": ["SOL/USD"]
}
```

### Performance Target

- Process 50 symbols in < 10 seconds
- Mostly filtering, minimal LLM calls
- Lowest consensus weight (0.5) - filtering role only

## Tactical Role

**Purpose**: Analyze chart patterns, support/resistance, indicator convergence and generate entry/exit signals.

**Default Provider**: DeepSeek-R1 (best reasoning for TA patterns)

### Key Features

#### OHLCV Candle Serialization
Configurable depth based on timeframe:
- 1m/5m: 500 candles
- 15m/1h: 200 candles
- 4h: 100 candles
- 1d: 50 candles

Full OHLCV data included for tactical analysis (vs. compact format for other roles).

#### Support/Resistance Calculation
Automatic calculation from recent price action:
- Finds significant highs/lows in lookback period (default 50 candles)
- Calculates distance to current price
- Provides percentage-based proximity metrics

#### Entry/Exit Level Extraction
Parses both structured JSON and natural language:
- Entry price
- Stop loss level
- Take profit target(s)
- Risk/reward ratio calculation

Handles multiple formats:
- `"entry": 50000`
- `Entry at $50,000`
- `entry: 50000` (with comma separators)

#### Multi-Timeframe Context
Optionally inject multiple timeframe analyses:
```python
context["multi_timeframe"] = {
    "4h": {"rsi": 45, "trend": "BULLISH"},
    "1d": {"rsi": 52, "trend": "NEUTRAL"}
}
```

### Example Usage

```python
from core.ai.roles.tactical import TacticalRole
from core.ai.types import AIRequest, RoleName
from core.types import Candle

tactical = TacticalRole()
request = AIRequest(
    role=RoleName.TACTICAL,
    user_prompt="Analyze BTC/USD for entry opportunities",
    context={
        "symbol": "BTC/USD",
        "timeframe": "1h",
        "candles": candles_list,  # List[Candle]
        "indicators": {
            "rsi": 45,
            "macd": {"line": 120, "signal": 115, "histogram": 5},
            "bb_upper": 51000,
            "bb_middle": 50000,
            "bb_lower": 49000
        }
    }
)
```

### Output Format

```json
{
  "action": "BUY",
  "confidence": 0.8,
  "reasoning": "RSI oversold + MACD crossover + support level",
  "entry": 50000,
  "stop_loss": 49000,
  "take_profit": 55000,
  "risk_reward": 5.0,
  "timeframe_alignment": "STRONG"
}
```

### Consensus Weight

Highest weight (1.5) - core technical analysis role.

## Fundamental Role

**Purpose**: Assess news sentiment, social buzz, macro events, and on-chain data for fundamental outlook.

**Default Provider**: Grok 4 (real-time web search + X/Twitter)

### Key Features

#### News Item Parsing
Handles both structured and unstructured news data:
- Structured: list of dicts with title/source/timestamp
- Unstructured: raw text parsed into news items
- Limits to 10 most recent items

#### Sentiment Scoring
Keyword-based sentiment analysis:
- Bullish keywords: "bullish", "positive", "growth", "rally", "breakout", "adoption"
- Bearish keywords: "bearish", "negative", "decline", "crash", "concern", "risk"
- Sentiment score: -1.0 (bearish) to 1.0 (bullish)

#### Event Risk Detection
Identifies high-risk events:
- Regulatory actions
- Hacks/security breaches
- Lawsuits/investigations
- Exchange delistings
- Event risk score: 0.0 (low) to 1.0 (high)

#### Web Search Integration
Prompts Grok 4 to search for recent news:
- Timeframe-aware lookback (6h for 1m, up to 2 weeks for 1d)
- Structured search instructions
- Real-time news vs. hallucinated data

### Example Usage

```python
from core.ai.roles.fundamental import FundamentalRole
from core.ai.types import AIRequest, RoleName

fundamental = FundamentalRole()
request = AIRequest(
    role=RoleName.FUNDAMENTAL,
    user_prompt="Analyze fundamental outlook",
    context={
        "symbol": "BTC/USD",
        "timeframe": "1h",
        "news": [
            {"title": "Bitcoin ETF approval", "source": "Bloomberg", "timestamp": "2024-01-15T10:00:00Z"},
            {"title": "Major exchange listing", "source": "CoinDesk", "timestamp": "2024-01-15T09:00:00Z"}
        ],
        "social": {"mentions_24h": 5000, "sentiment": "positive"},
        "onchain": {"active_addresses": 950000, "hash_rate": "350 EH/s"}
    }
)
```

### Output Format

```json
{
  "action": "BUY",
  "confidence": 0.7,
  "reasoning": "Positive news flow with ETF approval, low event risk",
  "sentiment_score": 0.6,
  "event_risk": 0.1,
  "social_volume": 0.8,
  "key_events": ["ETF approval", "Exchange listing"],
  "news_summary": "Two major positive developments in past 24h"
}
```

### Consensus Weight

Standard weight (1.0) - balanced with technical analysis.

## Strategist Role

**Purpose**: Evaluate proposed trades against portfolio exposure, risk limits, correlation, and provide go/no-go + position sizing.

**Default Provider**: o3-mini (strong reasoning, moderate cost)

### Key Features

#### Hard VETO Enforcement
Checks risk limits **BEFORE** LLM call (cost optimization):
- Max positions limit
- Max portfolio exposure %
- Per-trade risk %
- Returns synthetic VETO verdict immediately on breach

This is implemented in `evaluate()` override to avoid mutable state on singleton role instances.

#### Portfolio State Injection
Formats current portfolio for LLM analysis:
- Total equity and available balance
- Number of open positions
- Position details (symbol, side, size, entry, P&L)
- Total portfolio exposure

#### Position Sizing
Multiple sizing methods:
- **Kelly Criterion**: Optimal position size based on win rate and avg win/loss
- **Fixed Fraction**: Configurable percentage of equity
- **Risk-Based**: Based on distance to stop loss
- Takes most conservative recommendation

#### Correlation Analysis
Simple correlation penalty:
- Checks for same base asset (e.g., BTC/USD + BTC/EUR)
- Counts correlated positions
- Penalty increases with number of correlated positions
- Future: Could use actual price correlation

#### Risk Metrics
Calculates comprehensive risk metrics:
- Notional position size
- Risk per unit (distance to stop)
- Total trade risk in $ and %
- Risk as % of max allowed
- Exceeds limit flag

### Example Usage

```python
from core.ai.roles.strategist import StrategistRole
from core.ai.types import AIRequest, RoleName

strategist = StrategistRole()
request = AIRequest(
    role=RoleName.STRATEGIST,
    user_prompt="Evaluate trade risk",
    context={
        "symbol": "BTC/USD",
        "proposed_action": "BUY",
        "proposed_trade": {
            "size": 1.0,
            "entry_price": 50000,
            "stop_loss": 49000
        },
        "positions": [
            {
                "symbol": "ETH/USD",
                "side": "LONG",
                "quantity": 5.0,
                "avg_entry_price": 3000,
                "unrealized_pnl": 500,
                "notional": 15000
            }
        ],
        "portfolio": {
            "total_equity": 100000,
            "available_balance": 60000
        },
        "risk_limits": {
            "max_positions": 10,
            "max_exposure_pct": 0.95,
            "max_risk_per_trade_pct": 0.02,
            "historical_win_rate": 0.55,
            "avg_win_pct": 0.05,
            "avg_loss_pct": 0.02
        }
    }
)
```

### Output Format

```json
{
  "action": "BUY",
  "confidence": 0.75,
  "reasoning": "Risk within limits, low correlation with existing positions",
  "position_size_pct": 0.05,
  "portfolio_risk_pct": 0.18,
  "correlation_score": 0.2
}
```

Or for VETO:

```json
{
  "action": "VETO",
  "confidence": 1.0,
  "reasoning": "Hard risk limit breach: Max portfolio exposure: 96.0% >= 95.0%",
  "veto_reason": "Portfolio exposure limit exceeded"
}
```

### Consensus Weight

High weight (1.2) - risk management is critical.

## CoinDossier Integration

All roles produce outputs compatible with CoinDossier assessment fields:

### Tactical → CoinDossier Mapping
- `action` → `action` (BUY/SELL/HOLD)
- `confidence * 10` → `confidence` (1-10 scale)
- `metrics.entry` → `entry_zone[0]` (can add ±1% for zone)
- `metrics.stop_loss` → `stop_loss`
- `metrics.take_profit` → `take_profit[0]` (can add multiple targets)
- `reasoning` → `reasoning_summary`

### Fundamental → CoinDossier Enrichment
- `metrics.sentiment_score` → Narrative enrichment
- `metrics.event_risk` → `risk_level` mapping (0-0.3=low, 0.3-0.7=medium, 0.7+=high)
- `metrics.key_events_count` → News summary count

### Strategist → CoinDossier Risk
- `metrics.position_size_pct` → Position sizing guidance
- `metrics.portfolio_risk_pct` → Overall `risk_level`
- `action == "VETO"` → `action = "AVOID"`

## Testing

### Unit Tests (72 tests, 100% passing)

All roles have comprehensive test coverage:

#### Helper Functions
- Candle serialization (compact/full)
- Indicator serialization with Decimal conversion
- Portfolio state formatting
- Kelly criterion position sizing
- Risk metric calculations

#### Per-Role Tests
- Quick-reject heuristics (Screener)
- Prompt building with various contexts
- Response parsing (success/error cases)
- Edge case handling (NaN, Infinity, invalid types)
- Confidence normalization (0-100 and 0-1 scales)

#### Test Fixtures
- Sample candles (100 1h candles)
- Sample indicators (RSI, MACD, BB, volume)
- Sample portfolio positions

### Running Tests

```bash
# All role tests
python -m pytest tests/test_ai_roles.py -v

# Specific role
python -m pytest tests/test_ai_roles.py -k "screener" -v

# Specific test
python -m pytest tests/test_ai_roles.py::test_screener_quick_reject_low_volume -v

# With coverage
python -m pytest tests/test_ai_roles.py --cov=core.ai.roles --cov-report=html
```

## Performance Considerations

### Screener Optimization
- Quick-reject heuristics save ~70% of LLM calls
- Target: 50 symbols in < 10 seconds
- Batch processing reduces prompt overhead

### Tactical Candle Depth
- Configurable based on timeframe
- Shorter timeframes → more candles (higher resolution)
- Longer timeframes → fewer candles (broader context)

### Strategist Pre-Check
- Hard VETO before LLM call saves ~$0.034 per evaluation
- Avoids mutable state on singleton instances
- Returns synthetic verdict immediately

### Cost Tracking
All roles track token usage and cost:
- `response.tokens_in` - Input tokens
- `response.tokens_out` - Output tokens
- `response.cost_usd` - Estimated cost
- `response.latency_ms` - Call latency

## Common Patterns

### Confidence Normalization
All roles normalize confidence to [0.0, 1.0]:
1. Try to convert to float
2. Guard against NaN/Infinity (default to 0.5)
3. Detect 0-100 scale (if > 1.0 and <= 100.0, divide by 100)
4. Clamp to [0.0, 1.0]

```python
confidence = float(raw_confidence)
if not math.isfinite(confidence):
    confidence = 0.5
if 1.0 < confidence <= 100.0:
    confidence = confidence / 100.0
confidence = max(0.0, min(1.0, confidence))
```

### Action Validation
Coerce unknown actions to safe defaults:
```python
if raw_action in ("BUY", "SELL", "NEUTRAL", "VETO"):
    action = raw_action
else:
    action = "NEUTRAL"  # or "VETO" for Strategist on error
```

### Decimal Handling
Indicators use Decimal for precision:
```python
result = serialize_indicators(indicators)
# Converts all Decimal values to float for JSON serialization
```

## Future Enhancements

### Screener
- [ ] Machine learning-based quick-reject (train on historical data)
- [ ] Parallel LLM calls for remaining symbols
- [ ] Symbol prioritization by market cap/volume

### Tactical
- [ ] Chart pattern recognition (head-and-shoulders, triangles, etc.)
- [ ] Order book depth analysis
- [ ] Volume profile integration
- [ ] Multiple take-profit targets

### Fundamental
- [ ] Real-time news API integration (beyond Grok search)
- [ ] On-chain analysis (Glassnode, Nansen)
- [ ] Social media sentiment (Twitter, Reddit, Telegram)
- [ ] Crypto Fear & Greed Index integration

### Strategist
- [ ] Actual price correlation analysis (not just base asset matching)
- [ ] Sector-based grouping (DeFi, Layer-1, Meme, etc.)
- [ ] Dynamic position sizing based on market regime
- [ ] Portfolio optimization (Markowitz, Black-Litterman)
- [ ] Drawdown protection (reduce size after losses)

## References

- [Multi-Brain AI Architecture](./ARCHITECTURE.md#multi-brain-ai)
- [AI Provider Configuration](../core/ai/providers/README.md)
- [System Prompts](../core/ai/prompts/defaults.py)
- [Consensus Engine](../core/ai/consensus.py)
- [Issue #207](https://github.com/m0nklabs/cryptotrader/issues/207) - Parent issue
- [Issue #222](https://github.com/m0nklabs/cryptotrader/issues/222) - CoinDossier integration
