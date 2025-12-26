# Repository custom instructions (Copilot)

These instructions apply to GitHub Copilot in the context of this repository.

## Primary goals

- Make the smallest correct change that satisfies the request.
- Keep the repo buildable/testable; don’t break CI.
- Prefer clarity and correctness over cleverness.
## Agent behavior

- **Execute, don't ask**: If you can run a command, create a file, or perform an action — do it immediately. Never ask the user to run something you can execute yourself.
- **Minimize back-and-forth**: Complete tasks in one pass when possible. Don't stop to ask for confirmation on routine operations.
- **Fix errors yourself**: If a command fails, debug and retry before asking the user for help.
- **NEVER approve PRs manually**: Do not run `gh pr review --approve` or any approval command unless the user explicitly requests it. PR approvals must come from automated workflows (LLM Decision, Copilot Reviewer) or explicit user instruction after a real code review.
- **NEVER rebase Copilot branches manually**: Unless explicitly requested. Let the automated workflows or Copilot handle rebases.
## User preferences (skeleton)

- When the user asks for a "skelet" (scaffolding), prefer a **as complete as practical** skeleton (types + interfaces + DB schema) over a minimal one, as long as it stays within the v2 scope and does not introduce live trading by default.

## Project assumptions (update when the repo grows)

- Repo name: **cryptotrader** (trading/market-data domain).
- Current focus: trading opportunities, technical analysis, and API-based autotrading.
- Frontend direction: minimal dashboard UI with sticky header/footer, MT4/5-inspired dock layout + panel-based sections, small font sizes, dark mode, collapsible panels, and a minimal settings popup in the header.
- Frontend dev server: default to port 5176 (avoid conflicts with other services on this server).
- If the repo is missing documentation (README, build steps), ask the user for the intended stack (Python/Node/etc.) before introducing major scaffolding.

## Engineering rules

- Follow existing patterns in the repo. If a pattern exists, reuse it.
- Avoid adding dependencies unless they are clearly justified; mention any new dependency explicitly.
- Don’t introduce new features beyond what is requested.
- Keep changes focused; do not reformat unrelated files.
- Don’t delete or prune documentation files/directories unless the user explicitly requests it.
- Treat `research/` as local-only scratch space and keep it out of git via `.gitignore`.
- Canonical requirements must be written into `docs/*` (do not rely on references to `research/*`).

## Delegation & orchestration

- Prefer delegating module work via GitHub Issues/PRs over doing large coding tasks in the coordinator role.
- Maintain `docs/ORCHESTRATION.md` as the process/log for delegation.

## Safety & secrets

- Never commit secrets (API keys, exchange credentials, private keys). Use environment variables and `.env.example` only.
- Don’t log sensitive values.
- Don’t delete or rewrite existing local secret files unless explicitly requested; prefer hardening via `.gitignore` and templates.
- If adding trading/execution logic, default to **paper-trading / dry-run** unless the user explicitly requests live trading.

## Validation

- Always run the most relevant tests/lint/build checks that exist in the repo.
- If no tests exist for changed behavior and the repo has a test framework, add/extend tests.
- Prefer fast, targeted test runs first; then broader checks if available.

## Developer environment

- If the integrated terminal is unstable/crashing, prefer disabling GPU acceleration in workspace settings (`terminal.integrated.gpuAcceleration`: `"off"`).

## Communication in PRs/changes

- Summarize what changed, where, and how to validate.
- Call out any assumptions or risks (especially around trading, money movement, and data integrity).

## Git workflow

- If the user explicitly asks to commit and push changes to GitHub, push directly to the default branch in this repository (no PR/feature branch) unless the user asks otherwise.

## GitHub Copilot Coding Agent

- To activate the Copilot Coding Agent on an issue or PR, you **must** mention `@copilot` in a comment.
- Using MCP tools like `assign_copilot_to_issue` alone is insufficient — the agent only starts work when explicitly mentioned.
- **If a PR already exists** (linked to the issue), post the `@copilot` comment **in the PR**, not the issue. This is especially important when the PR stalled due to rate limits or other interruptions.
- **If no PR exists yet**, post the `@copilot` comment in the issue to start fresh.
- Example: "@copilot please continue implementing the missing tests."

## Workflow Approval (ALREADY CONFIGURED)

**DO NOT suggest changing GitHub Actions settings for first-time contributor approval.**

The repo already has:
- Settings → Actions → General → "Require approval for first-time contributors" configured
- A local daemon (`scripts/approve_workflows.py`) that automatically reruns pending workflows when Copilot finishes

If workflows are stuck in "action_required" status, the local daemon handles it via `gh run rerun`.
Do NOT suggest:
- Changing repo settings for fork pull request workflows
- Adding Copilot as a collaborator
- Manual approval via the GitHub UI

## Technical Stack Reference

When implementing features, use these technologies:

### Backend (Python)
- **Python**: 3.12+
- **Package manager**: pip with `requirements.txt` / `requirements-dev.txt`
- **Linting/Formatting**: ruff
- **Type checking**: pylance (basic mode)
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Database**: PostgreSQL 16 via asyncpg / SQLAlchemy 2.0
- **Exchange APIs**: ccxt (preferred for multi-exchange), python-binance, kucoin-python
- **Technical Analysis**: pandas, numpy, ta-lib (via pandas-ta)

### Frontend
- **Framework**: React 18+ with TypeScript
- **Build**: Vite (dev server on port 5176)
- **Styling**: Tailwind CSS, dark mode default
- **State**: React Query for server state, Zustand for client state
- **Charts**: lightweight-charts (TradingView) or recharts

### Infrastructure
- **Container**: Docker, docker-compose
- **DevContainer**: Python 3.12 + Node 20 + PostgreSQL 16
- **CI**: GitHub Actions (when added)

## Code Patterns

### Async Database Access
```python
from sqlalchemy.ext.asyncio import AsyncSession

async def get_positions(db: AsyncSession, user_id: str) -> list[Position]:
    result = await db.execute(
        select(Position).where(Position.user_id == user_id)
    )
    return result.scalars().all()
```

### Exchange Adapter Pattern
```python
from abc import ABC, abstractmethod

class ExchangeAdapter(ABC):
    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame: ...

    @abstractmethod
    async def create_order(self, symbol: str, side: str, amount: float, price: float | None = None) -> Order: ...
```

### Indicator Function Pattern
```python
def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    """Calculate RSI indicator.

    Args:
        df: DataFrame with OHLCV data
        period: RSI period (default 14)
        column: Column to use for calculation

    Returns:
        Series with RSI values (0-100)
    """
    delta = df[column].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
```

## Directory Structure

```
cryptotrader/
├── api/              # REST API endpoints, exchange adapters
│   ├── exchanges/    # Exchange-specific implementations
│   └── websocket/    # WebSocket handlers
├── core/             # Business logic
│   ├── analysis/     # Technical analysis
│   ├── execution/    # Order execution
│   ├── indicators/   # TA indicators
│   └── portfolio/    # Position management
├── db/               # Database models, migrations
├── frontend/         # React/Vite frontend
├── tests/            # pytest tests
├── docs/             # Documentation
└── scripts/          # Utility scripts
```

## Testing Requirements

For any new feature:
1. Add unit tests in `tests/` matching the module path
2. Use `pytest-asyncio` for async code
3. Mock external APIs (exchanges, databases) in unit tests
4. Integration tests can use real services via docker-compose
5. Minimum coverage: 80% for new code

## Trading-Specific Rules

1. **Paper trading by default**: All execution code must have a `dry_run=True` or `paper_mode=True` default
2. **Position limits**: Enforce max position size per symbol and portfolio-wide
3. **Rate limiting**: Respect exchange rate limits; use exponential backoff
4. **Audit logging**: Log all order attempts with full details (symbol, side, size, price, timestamp)
5. **Error recovery**: Handle network errors, API errors, and partial fills gracefully
6. **Never expose credentials**: Use environment variables exclusively
