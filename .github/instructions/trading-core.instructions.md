---
applyTo: "core/**/*.py,api/**/*.py"
---

## Trading Core Code Requirements

**CRITICAL**: This code handles financial operations. Follow these rules strictly.

### Safety First

1. **Paper trading by default** - All execution code MUST have `dry_run=True` or `paper_mode=True` as default
2. **Never expose credentials** - Use environment variables exclusively
3. **Audit logging** - Log all order attempts with: symbol, side, size, price, timestamp
4. **Position limits** - Enforce max position size per symbol and portfolio-wide
5. **Rate limiting** - Respect exchange rate limits; use exponential backoff

### Exchange Adapter Pattern

All exchange integrations must follow the adapter pattern:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd

@dataclass
class Order:
    id: str
    symbol: str
    side: str  # 'buy' | 'sell'
    amount: float
    price: float | None
    status: str
    timestamp: datetime

class ExchangeAdapter(ABC):
    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Fetch OHLCV candles."""
        ...

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float | None = None,
        dry_run: bool = True,  # MUST default to True
    ) -> Order:
        """Create an order. Defaults to paper trading."""
        ...
```

### Error Handling

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def fetch_with_retry(url: str) -> dict:
    """Fetch with exponential backoff."""
    ...
```

### Database Access (Async)

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def get_positions(db: AsyncSession, user_id: str) -> list[Position]:
    result = await db.execute(
        select(Position).where(Position.user_id == user_id)
    )
    return result.scalars().all()
```

### AI/LLM Safety Rules (when working on `core/ai/`)

1. **Budget caps** — Enforce daily/monthly USD spend limits for all LLM API calls
2. **Cost tracking** — Log `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms` per call
3. **Provider fallback** — If primary provider fails, try `fallback_provider` before giving up
4. **VETO safety** — Strategist role can hard-VETO any trade decision — never bypass this
5. **Prompt versioning** — Never overwrite active prompts; create new versions and activate explicitly
6. **Model pinning** — Pin specific model versions in provider configs

```python
from core.ai.providers.base import BaseProvider
from core.ai.types import ProviderConfig

class NewProvider(BaseProvider):
    async def complete(self, prompt: str, **kwargs) -> str:
        """Send prompt, track usage, return completion."""
        ...

    async def health_check(self) -> bool:
        """Verify provider is reachable."""
        ...

    async def close(self) -> None:
        """Clean up HTTP client resources."""
        ...
```

### What NOT to do:
- NEVER default `dry_run` to `False`
- NEVER log API keys or secrets
- NEVER make live trades without explicit user confirmation
- NEVER ignore rate limits
- NEVER bypass AI VETO decisions
- NEVER overwrite active system prompts (create new versions instead)
- NEVER make LLM API calls without cost tracking
