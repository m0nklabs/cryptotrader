# Roadmap V2: Path to the North Star

This document defines the comprehensive roadmap for cryptotrader v2, organized by **Epics** that guide the project toward the ultimate goal: **a semi-autonomous trading machine that generates consistent profit**.

> **North Star**: Profitability (PnL) is the primary success metric. Features are valuable only if they contribute to profit generation, risk control, or observability.

---

## 📋 Epic Overview

| Epic | Priority | Description | Status |
|------|----------|-------------|--------|
| [Epic 1: Backtesting & Validation](#epic-1-backtesting--validation) | 🔴 Critical | Prove profitability before live trading | 📋 Planned |
| [Epic 2: Execution & Automation](#epic-2-execution--automation) | 🟠 High | Live execution with multi-exchange support | 🚧 In Progress |
| [Epic 3: AI & LLM Integration](#epic-3-ai--llm-integration) | 🟡 Medium | AI-enhanced scoring and analysis | 📋 Planned |
| [Epic 4: Frontend Observability](#epic-4-frontend-observability) | 🟡 Medium | Real-time transparency and visualization | 📋 Planned |
| [Epic 5: Portfolio & Wallet](#epic-5-portfolio--wallet) | 🟡 Medium | Portfolio tracking and PnL monitoring | 📋 Planned |
| [Epic 6: Infrastructure & Operations](#epic-6-infrastructure--operations) | 🟢 Low | DevOps, automation, and reliability | 🚧 Partial |

---

## Epic 1: Backtesting & Validation

**Priority**: 🔴 Critical
**Goal**: Validate that strategies can generate profit using historical data before risking real capital.

> **Why Critical?** Without backtesting, we cannot prove the "profit" goal. This is the foundation for all live trading decisions.

### Issues

| Issue | Title | Status | Description |
|-------|-------|--------|-------------|
| #135 | Backtesting Framework | 📋 Planned | Core framework for historical data replay |
| — | Strategy Performance Metrics | 📋 Planned | Sharpe ratio, max drawdown, win rate, profit factor |
| — | Walk-Forward Analysis | 📋 Planned | Out-of-sample validation to prevent overfitting |
| — | Multi-Timeframe Backtest | 📋 Planned | Test strategies across multiple timeframes |
| — | Cost-Aware Backtesting | 📋 Planned | Include fees, slippage, spread in backtest results |

### Acceptance Criteria

- [ ] Run backtest on any symbol/timeframe with historical data
- [ ] Generate performance report with key metrics (Sharpe, drawdown, PnL)
- [ ] Compare strategies side-by-side
- [ ] Export results for analysis

### Dependencies

- ✅ Market data infrastructure (complete)
- ✅ Technical indicators (complete)
- ✅ Fee model (complete)

---

## Epic 2: Execution & Automation

**Priority**: 🟠 High
**Goal**: Enable live trading with human oversight, supporting multiple exchanges.

### Issues

| Issue | Title | Status | Description |
|-------|-------|--------|-------------|
| — | Bitfinex Live Adapter | 📋 Planned | Live order execution on Bitfinex (schema ready) |
| #131 | Multi-Exchange Support | 🚧 In Progress | Binance/KuCoin adapter interface |
| — | Binance Adapter | 📋 Planned | REST + WebSocket for Binance |
| — | KuCoin Adapter | 📋 Planned | REST + WebSocket for KuCoin |
| — | Trade Confirmation Flow | 📋 Planned | Human approval for large/risky trades |
| — | Order Status Tracking | 📋 Planned | Real-time order status updates |
| #134 | Paper Trading Improvements | 📋 Planned | Enhanced simulation accuracy |

### Acceptance Criteria

- [ ] Execute live orders on Bitfinex (with dry_run toggle)
- [ ] Unified adapter interface for all exchanges
- [ ] Human approval required for trades above threshold
- [ ] Full audit trail for all trade decisions

### Dependencies

- ✅ Paper trading engine (complete)
- ✅ Automation safety checks (complete)
- ✅ Risk management (complete)

---

## Epic 3: AI & LLM Integration

**Priority**: 🟡 Medium
**Goal**: Leverage LLMs for qualitative analysis and opportunity scoring.

### Issues

| Issue | Title | Status | Description |
|-------|-------|--------|-------------|
| — | Ollama Integration | 📋 Planned | Local LLM support via Ollama |
| — | API Provider Integration | 📋 Planned | OpenAI/Anthropic API support |
| — | LLM Scoring Engine | 📋 Planned | Rate opportunities with reasoning |
| — | Sentiment Analysis | 📋 Planned | Extract sentiment from market context |
| — | Signal Explanation | 📋 Planned | Human-readable LLM explanations for signals |

### Acceptance Criteria

- [ ] Configure Ollama endpoint for local LLM
- [ ] Configure API keys for cloud providers
- [ ] Generate qualitative score (0-100) with reasoning
- [ ] Fallback behavior when LLM unavailable

### Example Output

```json
{
  "score": 75,
  "reasoning": "Bullish divergence confirmed by RSI (25) indicating oversold conditions. MACD showing momentum shift with histogram turning positive. Volume remains below average which may limit upside. Recommend cautious entry with tight stop.",
  "confidence": "medium",
  "model": "llama3:8b"
}
```

### Dependencies

- ✅ Opportunity scoring (complete)
- ✅ Technical indicators (complete)

---

## Epic 4: Frontend Observability

**Priority**: 🟡 Medium
**Goal**: Provide real-time transparency into the trading system through the dashboard.

### Issues

| Issue | Title | Status | Description |
|-------|-------|--------|-------------|
| #107 | Indicator Overlays | 📋 Planned | Draw RSI, MACD, Bollinger on charts |
| #138 | Multi-Timeframe View | 📋 Planned | Show 1h trend context on 5m chart |
| — | Opportunity Explorer | 📋 Planned | List of opportunities sorted by quality |
| — | Visual Projections | 📋 Planned | Draw future price expectations on chart |
| — | Alert Indicators | 📋 Planned | Visual alerts for triggered signals |
| #142 | Keyboard Shortcuts | 📋 Planned | Quick navigation and actions |
| #148 | Drawing Tools | 📋 Planned | Manual annotations on charts |

### Sub-Features

#### Indicator Overlays
- RSI subplot with overbought/oversold lines
- MACD histogram with signal line
- Bollinger Bands on price chart
- Stochastic with zones
- ATR for volatility context

#### Multi-Timeframe Visualization
- Show higher timeframe trend direction
- Overlay key levels from larger timeframes
- Sync crosshairs across timeframe panels

#### Opportunity Explorer
- List view sorted by score/quality
- Filter by symbol, timeframe, signal direction
- Click to navigate to chart
- Quick stats (indicators contributing, reasons)

#### Visual Projections
- Forecast cones/bands on price chart
- Target price levels
- Stop loss visualization
- Risk/reward overlay

### Acceptance Criteria

- [ ] Indicators visible on chart (toggle on/off)
- [ ] Multi-TF context visible in opportunity view
- [ ] Opportunity list with click-to-chart navigation
- [ ] Projection overlay for active signals

### Dependencies

- ✅ Frontend dashboard skeleton (complete)
- ✅ Candlestick chart (complete)
- ✅ Technical indicators (complete)

---

## Epic 5: Portfolio & Wallet

**Priority**: 🟡 Medium
**Goal**: Comprehensive overview of portfolio performance and real-time PnL.

### Issues

| Issue | Title | Status | Description |
|-------|-------|--------|-------------|
| #136 | Portfolio Tracker | 📋 Planned | Real-time portfolio monitoring |
| — | Wallet Overview | 📋 Planned | Exchange balances across all connected accounts |
| — | Position Details | 📋 Planned | Per-position PnL, entry, current price |
| — | Performance Charts | 📋 Planned | Equity curve, drawdown chart |
| — | Trade History | 📋 Planned | Complete audit of all trades |
| #145 | Data Export | 📋 Planned | CSV/JSON export for analysis |

### Acceptance Criteria

- [ ] Show total portfolio value (all exchanges)
- [ ] Per-position breakdown with unrealized PnL
- [ ] Equity curve with daily/weekly/monthly views
- [ ] Drawdown visualization
- [ ] Export trade history

### Dependencies

- ✅ Paper trading positions (complete)
- ✅ Database persistence (complete)
- 📋 Live execution adapters (planned)

---

## Epic 6: Infrastructure & Operations

**Priority**: 🟢 Low (ongoing)
**Goal**: Improve reliability, monitoring, and developer experience.

### Issues

| Issue | Title | Status | Description |
|-------|-------|--------|-------------|
| #137 | Docker Compose Setup | 📋 Planned | One-command local development |
| — | Scheduled Jobs | 📋 Planned | Automated backfill/gap repair |
| #132 | WebSocket Real-time | ✅ Complete | Real-time price updates |
| #133 | Price Alerts | 📋 Planned | Notifications for price levels |
| #144 | Telegram/Discord Notifications | 📋 Planned | External alert channels |
| #147 | Rate Limit Monitor | 📋 Planned | Exchange API rate limit tracking |
| #106 | System Health Panel | 📋 Planned | Backend health visibility in UI |

### Acceptance Criteria

- [ ] `docker-compose up` starts full stack
- [ ] Scheduled jobs run reliably (systemd/cron)
- [ ] Alert notifications delivered (Telegram/Discord)
- [ ] Rate limits visible and respected

### Dependencies

- ✅ Systemd templates (complete)
- ✅ WebSocket provider (complete)

---

## Dependency Graph

```
Epic 1 (Backtesting)
    ↓
Epic 2 (Execution) ←──── Epic 5 (Portfolio)
    ↓
Epic 3 (AI/LLM)
    ↓
Epic 4 (Frontend) ←──── Epic 5 (Portfolio)
    ↓
Epic 6 (Infrastructure) — ongoing
```

**Critical Path**: Backtesting & Validation → Execution & Automation → AI & LLM Integration → Frontend Observability

---

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| **Backtest Sharpe** | > 1.5 | Backtesting framework output |
| **Max Drawdown** | < 15% | Drawdown monitor |
| **Win Rate** | > 55% | Trade history analysis |
| **Execution Latency** | < 500ms | Order timestamp logs |
| **Signal Explainability** | 100% | All signals have reasons |
| **Uptime** | > 99% | Health monitoring |

---

## Changelog

| Date | Change |
|------|--------|
| 2024-12 | Initial roadmap created based on project evaluation |

---

## Related Documents

- [TODO.md](TODO.md) — Feature backlog and status
- [FEATURES.md](FEATURES.md) — Detailed feature documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design
- [RISK_MANAGEMENT.md](RISK_MANAGEMENT.md) — Position sizing and limits
