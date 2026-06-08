## Summary

<!-- Brief description of what this PR does -->

## Related Issue

Fixes #<!-- issue number -->

## Report Comment

<!-- Required for any code change. Link the dedicated PR comment that reports owner, scope, touched files, validation, and remaining risks. -->

<!-- Example: https://github.com/m0nklabs/cryptotrader/pull/123#issuecomment-0000000000 -->

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 📚 Documentation update
- [ ] 🔧 Refactoring (no functional changes)
- [ ] 🧪 Test coverage improvement

## Checklist

### General
- [ ] My code follows the existing patterns in this repo
- [ ] I have added/updated tests for my changes
- [ ] All new and existing tests pass (`pytest`)
- [ ] Linting passes (`ruff check .`)
- [ ] I have updated documentation if needed
- [ ] I posted a dedicated PR comment report for this code change with owner, scope, touched files, validation, and remaining risks
- [ ] This branch does not include unrelated stacked commits outside the stated issue/scope

### Trading-Specific (if applicable)
- [ ] Paper trading is the default (`dry_run=True` or `paper_mode=True`)
- [ ] No credentials/secrets are hardcoded
- [ ] All order attempts are logged with full details
- [ ] Position limits are enforced
- [ ] Error handling covers network errors, API errors, partial fills

### AI/Multi-Brain (if applicable)
- [ ] Budget caps enforced (daily/monthly limits)
- [ ] Cost tracking implemented (tokens_in, tokens_out, cost_usd, latency_ms)
- [ ] VETO logic not bypassed (Strategist can block any trade)
- [ ] Prompt changes create new versions (no overwriting active prompts)
- [ ] Provider model versions are pinned
- [ ] Fallback provider configured for critical paths

## Testing Instructions

<!-- How can reviewers test this change? -->

```bash
# Example commands to run
pytest tests/test_<module>.py -v
```

## Screenshots (if UI changes)

<!-- Add screenshots here if relevant -->
