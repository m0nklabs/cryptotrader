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
