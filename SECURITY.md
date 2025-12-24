# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT open a public issue**
2. Email the maintainer directly or use GitHub's private vulnerability reporting
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work with you to understand and address the issue.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| v2.x    | ✅ Yes             |
| < v2.0  | ❌ No              |

## Trading Safety

This project handles **financial operations**. Extra care is required:

### Credentials & Secrets

- ❌ **Never commit** API keys, secrets, or private keys
- ✅ Use `.env` files (gitignored) and `.env.example` templates
- ✅ Use environment variables in production
- ✅ Rotate credentials if exposed

### Paper Trading Default

All trading/execution code **must default to paper trading**:

```python
async def execute_order(
    symbol: str,
    side: str,
    size: Decimal,
    dry_run: bool = True,  # ALWAYS default True
) -> OrderResult:
    ...
```

Live trading should only be enabled through explicit configuration.

### Audit Logging

All order attempts must be logged with:
- Timestamp
- Symbol
- Side (buy/sell)
- Size
- Price
- Order type
- Result (success/failure/error)

### Position Limits

Enforce limits to prevent catastrophic losses:
- Max position size per symbol
- Max portfolio exposure
- Daily loss limits

### Rate Limiting

Respect exchange rate limits:
- Implement exponential backoff
- Cache where appropriate
- Monitor API usage

## Dependencies

We use Dependabot to keep dependencies updated. Review and merge security updates promptly.

## Pre-commit Hooks

Pre-commit hooks check for:
- Accidental secret commits
- Private key patterns
- Large binary files

Install with:
```bash
pip install pre-commit
pre-commit install
```
