---
applyTo: "**/tests/**/*.py"
---

## Python Test Requirements

When writing or modifying Python tests, follow these guidelines:

1. **Use pytest** - All tests use pytest with pytest-asyncio for async code
2. **Table-driven tests** - Use `@pytest.mark.parametrize` for multiple test cases
3. **Mock external APIs** - Always mock exchange APIs (ccxt, binance, etc.) in unit tests
4. **Async testing** - Use `@pytest.mark.asyncio` for async test functions
5. **Test isolation** - Each test should be independent and not rely on other tests' state
6. **Fixtures** - Use pytest fixtures for common setup, define in `conftest.py`
7. **Coverage** - Aim for 80%+ coverage on new code
8. **Naming** - Use descriptive names: `test_<function>_<scenario>_<expected>`

### Example patterns:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_fetch_ohlcv_returns_dataframe():
    """Test that fetch_ohlcv returns a properly formatted DataFrame."""
    ...

@pytest.mark.parametrize("symbol,expected", [
    ("BTCUSD", "BTCUSDT"),
    ("ETHUSDT", "ETHUSDT"),
])
def test_normalize_symbol(symbol, expected):
    assert normalize_symbol(symbol) == expected
```

### What NOT to do:
- Don't use `time.sleep()` in tests - use mocks or async patterns
- Don't make real API calls in unit tests
- Don't hardcode API keys or secrets
- Don't make real LLM API calls - always mock providers

### AI Module Test Patterns

When testing `core/ai/` code:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.ai.types import ProviderName, RoleName, RoleVerdict

@pytest.fixture
def mock_provider():
    """Mock LLM provider that returns canned responses."""
    provider = AsyncMock()
    provider.complete.return_value = '{"action": "BUY", "confidence": 0.75, "reasoning": "test"}'
    provider.health_check.return_value = True
    provider.close.return_value = None
    return provider

@pytest.fixture
def mock_db_session():
    """Mock async database session."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session

@pytest.mark.asyncio
async def test_consensus_requires_veto_respected(mock_provider):
    """Test that Strategist VETO blocks trade execution."""
    ...

@pytest.mark.asyncio
async def test_provider_fallback_on_failure(mock_provider):
    """Test fallback to secondary provider when primary fails."""
    mock_provider.complete.side_effect = ConnectionError("API down")
    ...
```

### Database Fixture Pattern

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
async def db_session():
    """Create an async test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
```
