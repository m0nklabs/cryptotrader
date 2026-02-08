# Consensus Engine & Router Production Features (P4)

This document describes the production-ready features added to the consensus engine and router for resilience and robustness.

## Consensus Engine Enhancements

### 1. Soft VETO Mode

The consensus engine now supports two VETO modes:

- **Hard VETO** (default): Any role's VETO immediately blocks the trade, returning NEUTRAL with confidence 0.0
- **Soft VETO**: VETO reduces final confidence by 50% but allows the decision to proceed based on other roles

```python
# Hard VETO (default)
engine = ConsensusEngine(veto_mode="hard")

# Soft VETO (reduces confidence)
engine = ConsensusEngine(veto_mode="soft")
```

**Use case**: Soft VETO is useful for advisory warnings that should influence but not block decisions (e.g., minor risk concerns that don't warrant a full veto).

### 2. Agreement Multiplier

When all roles unanimously agree on a non-NEUTRAL action, confidence is boosted by the agreement multiplier.

```python
engine = ConsensusEngine(
    agreement_multiplier=1.15,  # 15% boost for unanimous agreement
)
```

- Default: 1.15 (15% boost)
- Final confidence is capped at 1.0
- Only applies when ≥2 roles all vote for the same action

**Use case**: Rewards high-confidence decisions where all experts agree.

### 3. Confidence Calibration

Historical accuracy tracking with Bayesian weight adjustment:

```python
engine = ConsensusEngine(
    enable_calibration=True,
    min_calibration_samples=10,
)

# After each trade outcome is known:
engine.update_role_accuracy("tactical", was_correct=True)
```

- Roles with accuracy > 50% get increased weight
- Roles with accuracy < 50% get decreased weight
- Uses exponential moving average (EMA) for smooth updates
- Requires minimum sample size before calibration activates

**Use case**: Automatically adapts to role performance over time, giving more weight to consistently accurate roles.

### 4. Enhanced Decision Logging

All decisions now include:
- Full role reasoning (truncated to 100 chars for readability)
- Confidence values
- Soft VETO indicators
- Decision chain audit trail

```python
decision = engine.aggregate(verdicts)
print(decision.reasoning)
# Output: "Consensus: BUY (conf=0.85) | screener: BUY (conf=0.8) [Strong momentum...] | tactical: BUY (conf=0.9) [Bullish breakout...]"
```

---

## Router Enhancements

### 1. Per-Role Timeouts

Different roles have different timeout requirements:

```python
router = LLMRouter()
# Default timeouts:
# - Screener: 30s
# - Tactical: 60s (longer for reasoning models)
# - Fundamental: 30s
# - Strategist: 30s
```

- Timeouts prevent slow roles from blocking the pipeline
- Timed-out roles are excluded from consensus (partial evaluation)
- Configurable per role: `router._role_timeouts[RoleName.TACTICAL] = 90.0`

**Use case**: DeepSeek-R1 and o3-mini reasoning models may take longer; timeout ensures responsiveness.

### 2. Circuit Breaker (Per Provider)

Prevents cascading failures when a provider is down:

```python
router = LLMRouter(enable_circuit_breaker=True)
```

**State machine**:
- **CLOSED** (normal): All requests allowed
- **OPEN** (failure): Requests blocked after 5 consecutive failures
- **HALF_OPEN** (testing): After 5 min cooldown, allows 1 test request

**Configuration**:
- Failure threshold: 5 consecutive failures
- Cooldown: 5 minutes
- Half-open test requests: 1

**Management**:
```python
# Check status
status = router.get_circuit_breaker_status()
# {"deepseek": {"state": "open", "failure_count": 5, "last_failure_time": 123456}}

# Manual reset (admin operation)
router.reset_circuit_breaker(ProviderName.DEEPSEEK)
```

**Use case**: When a provider goes down, circuit breaker prevents repeated failed requests, allowing other providers to serve requests.

### 3. Partial Evaluation

Graceful degradation when some roles fail or timeout:

```python
router = LLMRouter(min_roles_required=2)
```

- If ≥ `min_roles_required` respond → consensus decision
- If < `min_roles_required` respond → NEUTRAL with confidence 0.0
- Failed/timed-out roles logged for debugging

**Use case**: CoinDossier generation can proceed with partial data (e.g., Tactical + Fundamental only), avoiding full failure if Screener times out.

### 4. Database Persistence

Usage logs and decisions are automatically persisted:

```python
from db.session import get_db

async with get_db() as db:
    decision = await router.evaluate_opportunity(
        symbol="BTC/USD",
        timeframe="1h",
        db_session=db,  # Enables persistence
    )
```

- Atomic transaction: decision + all usage records written together
- Database schema: `ai_usage_log`, `ai_decisions`
- Budget tracking: tokens, cost, latency per role

**Use case**: Cost monitoring, performance analysis, audit trails for regulatory compliance.

---

## CoinDossier Integration Notes

The router/consensus enhancements were designed with CoinDossier in mind:

1. **Partial evaluation** → Dossiers can be generated even if some roles fail
2. **Timeouts** → No UI freezes while generating dossiers
3. **Circuit breaker** → Degraded service instead of total failure
4. **Soft VETO** → Advisory warnings don't block dossier generation

**Philosophy**: *Degraded-but-fast > perfect-but-hanging*

---

## Testing

Comprehensive test coverage:

- **Consensus tests**: 20 original + 13 advanced = 33 tests
- **Router tests**: 12 tests (circuit breaker, timeouts, partial eval)
- **Total AI tests**: 159 passing

Run tests:
```bash
pytest tests/test_ai_consensus.py tests/test_ai_consensus_advanced.py -v
pytest tests/test_ai_router.py -v
```

---

## Performance Characteristics

| Feature | Overhead | Benefit |
|---------|----------|---------|
| Circuit breaker | ~1ms per request | Prevents cascading failures |
| Timeout | 0ms (async) | Ensures responsiveness |
| Calibration | ~5ms per aggregation | Improves accuracy over time |
| DB persistence | ~10-20ms (async) | Audit trail, cost tracking |

---

## Future Enhancements

Potential improvements (not in scope for P4):

1. **Dynamic timeout adjustment** based on provider latency history
2. **Cost-based routing** (prefer cheaper providers when confidence is similar)
3. **A/B testing framework** for prompt versions
4. **Role-level circuit breakers** (not just provider-level)
5. **Consensus caching** for repeated symbol evaluations

---

## Migration Notes

Existing code is backward-compatible:

- Default behavior unchanged (hard VETO, no calibration)
- Timeouts don't affect fast providers
- Circuit breaker enabled by default but only activates on failures
- DB persistence optional (pass `db_session=None` to disable)

**No breaking changes.**
