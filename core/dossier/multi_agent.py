"""Multi-agent PairDossier prediction service — issue #231.

Runs all configured AI roles against a trading pair in parallel,
aggregates verdicts via ConsensusEngine, stores results in pair_predictions,
and caches results for 5 minutes to avoid re-running the same pair.

Usage:
    svc = MultiAgentPredictionService()
    result = await svc.predict("bitfinex", "BTCUSD")
    # result.consensus_action: "BUY" | "SELL" | "NEUTRAL" | "VETO"
    # result.predictions: list of per-role predictions with confidence
    # result.rankings: top models by recent accuracy

Architecture:
    DossierService._gather_stats()  →  stats dict (price, RSI, MACD, etc.)
    MultiAgentPredictionService     →  runs roles in parallel via Guardian
    ConsensusEngine                 →  weighted vote → final decision
    pair_predictions table          →  append-only prediction log
    prediction_cache                →  5-min TTL deduplication
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEBUG = os.environ.get("MULTIBRAIN_DEBUG", "").lower() in ("1", "true", "yes")


def _debug(msg: str) -> None:
    if DEBUG:
        print(f"🐛 [MultiBrain] {msg}", flush=True)
    logger.debug(msg)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RolePrediction:
    """Single role's prediction for a pair."""

    role: str
    action: str  # BUY | SELL | NEUTRAL | VETO
    confidence: float  # 0.0 – 1.0
    reasoning: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    db_id: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MultiAgentResult:
    """Aggregated result from multi-agent prediction run."""

    exchange: str
    symbol: str
    consensus_action: str  # BUY | SELL | NEUTRAL | VETO
    consensus_confidence: float  # weighted
    predictions: list[RolePrediction] = field(default_factory=list)
    reasoning: str = ""
    vetoed_by: str | None = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    from_cache: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "consensus_action": self.consensus_action,
            "consensus_confidence": round(self.consensus_confidence, 4),
            "reasoning": self.reasoning,
            "vetoed_by": self.vetoed_by,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "from_cache": self.from_cache,
            "timestamp": self.timestamp,
            "predictions": [p.to_dict() for p in self.predictions],
        }


# ---------------------------------------------------------------------------
# System prompts per role (GLM-optimized, concise for fast inference)
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "screener": """You are a crypto market screener. Analyze technical indicators and decide if this pair is WORTH deeper analysis.
Respond ONLY with valid JSON:
{"action": "BUY"|"SELL"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": "1-2 sentences"}
Be decisive. Low confidence = NEUTRAL.""",
    "tactical": """You are a crypto technical analyst specializing in price action and chart patterns.
Based on the indicators provided, give a trading signal.
Respond ONLY with valid JSON:
{"action": "BUY"|"SELL"|"NEUTRAL", "confidence": 0.0-1.0, "reasoning": "2-3 sentences", "entry": price, "stop_loss": price, "take_profit": price}
If you cannot determine a clear signal, use NEUTRAL with low confidence.""",
    "strategist": """You are a risk-focused crypto trading strategist. Your job is to VETO bad trades.
You see the screener and tactical opinions. Apply risk management thinking.
Respond ONLY with valid JSON:
{"action": "BUY"|"SELL"|"NEUTRAL"|"VETO", "confidence": 0.0-1.0, "reasoning": "2-3 sentences"}
VETO only if there is a clear risk reason (news, overextension, etc). Otherwise confirm or adjust.""",
}

# Role weights for consensus (strategist has final-say veto power)
ROLE_WEIGHTS: dict[str, float] = {
    "screener": 0.8,
    "tactical": 1.5,
    "strategist": 1.2,
}


# ---------------------------------------------------------------------------
# Multi-agent service
# ---------------------------------------------------------------------------


class MultiAgentPredictionService:
    """Runs all roles in parallel, aggregates via consensus, stores results."""

    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        db_url: str | None = None,
        guardian_host: str | None = None,
        guardian_api_key: str | None = None,
        primary_model: str | None = None,
        strategist_model: str | None = None,
    ):
        self.db_url = db_url or os.environ.get(
            "DATABASE_URL",
            "postgresql://cryptotrader:cryptotrader@localhost:5432/cryptotrader",
        )
        self.guardian_host = guardian_host or os.environ.get("GUARDIAN_HOST", "http://localhost:11434")
        self.api_key = guardian_api_key or os.environ.get("GUARDIAN_API_KEY", "")
        # All roles use GLM by default; strategist can optionally use Qwen3-Thinking
        self.primary_model = primary_model or os.environ.get("MULTIBRAIN_PRIMARY_MODEL", "GLM-4.7-Flash")
        self.strategist_model = strategist_model or os.environ.get("MULTIBRAIN_STRATEGIST_MODEL", self.primary_model)

        self._headers = {"Content-Type": "application/json"}
        if self.api_key:
            self._headers["Authorization"] = f"Bearer {self.api_key}"

        _debug(f"📋 Config: primary={self.primary_model}, strategist={self.strategist_model}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def predict(
        self,
        exchange: str,
        symbol: str,
        horizon: str = "24h",
        stats: dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> MultiAgentResult:
        """Run multi-agent prediction for a pair.

        1. Check 5-minute cache (skip if force_refresh)
        2. Gather stats (price, RSI, MACD, etc.) if not provided
        3. Run screener + tactical in parallel, then strategist
        4. Aggregate via ConsensusEngine
        5. Store all predictions in pair_predictions table
        6. Cache result

        Args:
            exchange: Exchange code (e.g. "bitfinex")
            symbol: Trading pair (e.g. "BTCUSD")
            horizon: Prediction horizon (e.g. "24h", "1h", "4h")
            stats: Pre-computed stats dict (skips DB fetch if provided)
            force_refresh: Bypass cache

        Returns:
            MultiAgentResult with consensus + per-role predictions
        """
        cache_key = f"{exchange}:{symbol}:{horizon}"

        # Cache check
        if not force_refresh:
            cached = await self._get_cache(cache_key)
            if cached:
                _debug(f"✅ Cache hit for {cache_key}")
                return cached

        _debug(f"🔄 Running multi-agent prediction for {cache_key}")

        # Gather stats if not provided
        if stats is None:
            from core.dossier.service import DossierService

            dossier_svc = DossierService(db_url=self.db_url)
            try:
                stats = await dossier_svc._gather_stats(exchange, symbol)
            except Exception as e:
                logger.error("Failed to gather stats for %s:%s: %s", exchange, symbol, e)
                stats = {"price": 0, "error": str(e)}

        # Run screener + tactical in parallel
        _debug("📊 Running screener + tactical in parallel")
        start_total = time.monotonic()

        screener_task = asyncio.create_task(
            self._call_role("screener", exchange, symbol, stats, horizon, self.primary_model)
        )
        tactical_task = asyncio.create_task(
            self._call_role("tactical", exchange, symbol, stats, horizon, self.primary_model)
        )
        screener_pred, tactical_pred = await asyncio.gather(screener_task, tactical_task)
        _debug(
            f"📊 screener={screener_pred.action}({screener_pred.confidence:.2f}), tactical={tactical_pred.action}({tactical_pred.confidence:.2f})"
        )

        # Run strategist with context from first two roles
        strategist_context = {
            "screener_opinion": f"{screener_pred.action} (conf={screener_pred.confidence:.2f}): {screener_pred.reasoning}",
            "tactical_opinion": f"{tactical_pred.action} (conf={tactical_pred.confidence:.2f}): {tactical_pred.reasoning}",
        }
        strategist_pred = await self._call_role(
            "strategist",
            exchange,
            symbol,
            stats,
            horizon,
            self.strategist_model,
            extra_context=strategist_context,
        )
        _debug(f"📊 strategist={strategist_pred.action}({strategist_pred.confidence:.2f})")

        total_latency = (time.monotonic() - start_total) * 1000
        predictions = [screener_pred, tactical_pred, strategist_pred]

        # Consensus via weighted voting
        consensus = self._aggregate(predictions)

        result = MultiAgentResult(
            exchange=exchange,
            symbol=symbol,
            consensus_action=consensus["action"],
            consensus_confidence=consensus["confidence"],
            predictions=predictions,
            reasoning=consensus["reasoning"],
            vetoed_by=consensus.get("vetoed_by"),
            total_cost_usd=sum(p.cost_usd for p in predictions),
            total_latency_ms=total_latency,
        )

        # Store in DB (non-blocking — don't fail prediction if DB is down)
        try:
            prediction_ids = await self._store_predictions(exchange, symbol, horizon, predictions, stats)
            for pred, db_id in zip(predictions, prediction_ids):
                pred.db_id = db_id
        except Exception as e:
            logger.warning("Failed to store predictions (non-fatal): %s", e)

        # Cache result
        try:
            await self._set_cache(cache_key, result)
        except Exception as e:
            logger.warning("Failed to cache result (non-fatal): %s", e)

        logger.info(
            "🧠 %s:%s → %s (conf=%.2f) [%d roles, %.0fms, $%.6f]",
            exchange,
            symbol,
            result.consensus_action,
            result.consensus_confidence,
            len(predictions),
            total_latency,
            result.total_cost_usd,
        )

        return result

    async def predict_batch(
        self,
        exchange: str,
        symbols: list[str],
        horizon: str = "24h",
    ) -> list[MultiAgentResult]:
        """Run predictions for multiple pairs (sequential to protect GPU)."""
        results = []
        for symbol in symbols:
            try:
                result = await self.predict(exchange, symbol, horizon)
                results.append(result)
                # Small delay between pairs to avoid overwhelming GPU
                await asyncio.sleep(2)
            except Exception as e:
                logger.error("Prediction failed for %s:%s: %s", exchange, symbol, e)
        return results

    async def get_rankings(
        self,
        exchange: str = "bitfinex",
        timeframe_days: int = 7,
        min_samples: int = 3,
        limit: int = 10,
    ) -> list[dict]:
        """Get model/role accuracy rankings for a time window.

        Returns top models ranked by directional prediction accuracy
        for pairs with at least min_samples evaluated predictions.

        Args:
            exchange: Exchange to filter on
            timeframe_days: Look-back window in days
            min_samples: Minimum predictions to qualify for ranking
            limit: Max results to return
        """
        import asyncpg

        try:
            conn = await asyncpg.connect(self.db_url, timeout=5)
            try:
                rows = await conn.fetch(
                    """
                    SELECT
                        model,
                        role,
                        COUNT(*) AS total,
                        SUM(CASE WHEN outcome_correct THEN 1 ELSE 0 END) AS correct,
                        ROUND(
                            100.0 * SUM(CASE WHEN outcome_correct THEN 1 ELSE 0 END) / COUNT(*),
                            1
                        ) AS accuracy_pct,
                        AVG(confidence) AS avg_confidence,
                        AVG(latency_ms) AS avg_latency_ms
                    FROM pair_predictions
                    WHERE
                        exchange = $1
                        AND outcome_correct IS NOT NULL
                        AND created_at >= NOW() - INTERVAL '$2 days'
                    GROUP BY model, role
                    HAVING COUNT(*) >= $3
                    ORDER BY accuracy_pct DESC, total DESC
                    LIMIT $4
                    """,
                    exchange,
                    timeframe_days,
                    min_samples,
                    limit,
                )
                return [dict(r) for r in rows]
            finally:
                await conn.close()
        except Exception as e:
            logger.error("Failed to get rankings: %s", e)
            return []

    async def mark_outcomes(
        self,
        exchange: str = "bitfinex",
        max_hours: int = 48,
    ) -> int:
        """Evaluate pending predictions whose horizon has elapsed.

        Fetches current prices and marks outcome_correct for all
        predictions that are past their horizon and still pending.

        Returns number of predictions evaluated.
        """
        import asyncpg

        try:
            conn = await asyncpg.connect(self.db_url, timeout=5)
            try:
                # Get pending predictions older than their horizon
                rows = await conn.fetch(
                    """
                    SELECT id, symbol, action, confidence, price_at_prediction, horizon, created_at
                    FROM pair_predictions
                    WHERE
                        exchange = $1
                        AND outcome_correct IS NULL
                        AND price_at_prediction > 0
                        AND created_at < NOW() - INTERVAL '1 hour'
                        AND created_at > NOW() - INTERVAL '$2 hours'
                    ORDER BY created_at ASC
                    LIMIT 100
                    """,
                    exchange,
                    max_hours,
                )

                if not rows:
                    return 0

                # Get current prices for all unique symbols
                from core.dossier.service import DossierService

                dossier_svc = DossierService(db_url=self.db_url)
                symbols_needed = list({r["symbol"] for r in rows})
                current_prices: dict[str, float] = {}
                for sym in symbols_needed:
                    try:
                        stats = await dossier_svc._gather_stats(exchange, sym)
                        current_prices[sym] = float(stats.get("price", 0))
                    except Exception:
                        pass

                # Evaluate outcomes
                evaluated = 0
                for row in rows:
                    symbol = row["symbol"]
                    current_price = current_prices.get(symbol, 0)
                    if not current_price:
                        continue

                    pred_price = float(row["price_at_prediction"])
                    pct_change = (current_price - pred_price) / pred_price * 100 if pred_price > 0 else 0
                    action = row["action"]

                    correct = (
                        (action == "BUY" and pct_change > 0.5)
                        or (action == "SELL" and pct_change < -0.5)
                        or (action == "NEUTRAL" and abs(pct_change) <= 2.0)
                    )

                    await conn.execute(
                        """
                        UPDATE pair_predictions
                        SET outcome_correct = $1,
                            price_at_outcome = $2,
                            outcome_evaluated_at = NOW()
                        WHERE id = $3
                        """,
                        correct,
                        current_price,
                        row["id"],
                    )
                    evaluated += 1

                _debug(f"📈 Evaluated {evaluated} pending predictions")
                return evaluated
            finally:
                await conn.close()
        except Exception as e:
            logger.error("Failed to mark outcomes: %s", e)
            return 0

    # ------------------------------------------------------------------
    # Internal: LLM calls
    # ------------------------------------------------------------------

    async def _call_role(
        self,
        role: str,
        exchange: str,
        symbol: str,
        stats: dict[str, Any],
        horizon: str,
        model: str,
        extra_context: dict[str, str] | None = None,
    ) -> RolePrediction:
        """Call a single role and return its prediction."""
        system_prompt = SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["screener"])
        user_prompt = self._build_prompt(role, exchange, symbol, stats, horizon, extra_context)

        start = time.monotonic()
        try:
            response = await self._query_guardian(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            logger.error("Role %s failed for %s:%s: %s", role, exchange, symbol, e)
            return RolePrediction(
                role=role,
                action="NEUTRAL",
                confidence=0.0,
                reasoning=f"Error: {e}",
                model=model,
                provider="guardian",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        latency = (time.monotonic() - start) * 1000

        # Parse JSON response
        action, confidence, reasoning = self._parse_role_response(response.get("text", ""), role)

        return RolePrediction(
            role=role,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            model=model,
            provider="guardian",  # ProviderName.GUARDIAN
            tokens_in=response.get("tokens_in", 0),
            tokens_out=response.get("tokens_out", 0),
            latency_ms=latency,
            cost_usd=0.0,
        )

    def _build_prompt(
        self,
        role: str,
        exchange: str,
        symbol: str,
        stats: dict[str, Any],
        horizon: str,
        extra_context: dict[str, str] | None = None,
    ) -> str:
        """Build role-specific prompt from stats."""
        parts = [
            f"Pair: {symbol} on {exchange} | Horizon: {horizon}",
            "",
            f"Price: ${stats.get('price', 0):,.4f}",
            f"24h change: {stats.get('change_24h', 0):+.2f}%",
            f"7d change: {stats.get('change_7d', 'N/A')}{'%' if isinstance(stats.get('change_7d'), (int, float)) else ''}",
            f"RSI(14): {stats.get('rsi', 'N/A')}",
            f"EMA trend: {stats.get('ema_trend', 'N/A')}",
            f"MACD: {stats.get('macd_signal', 'N/A')}",
            f"Volume ratio (vs avg): {stats.get('volume_ratio', 'N/A')}x",
            f"Support: ${stats.get('support_level', 0):,.4f} | Resistance: ${stats.get('resistance_level', 0):,.4f}",
        ]

        if extra_context:
            parts.append("")
            parts.append("=== Previous Role Opinions ===")
            for k, v in extra_context.items():
                parts.append(f"{k}: {v}")

        parts.append("")
        parts.append(f"Give your {role} assessment. Respond with JSON only.")

        return "\n".join(parts)

    async def _query_guardian(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """Query the Guardian proxy with OpenAI-compat format."""
        async with httpx.AsyncClient(
            base_url=self.guardian_host,
            timeout=httpx.Timeout(180.0),
            headers=self._headers,
        ) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "temperature": 0.0,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage", {})

        return {
            "text": text,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
        }

    def _parse_role_response(self, text: str, role: str) -> tuple[str, float, str]:
        """Parse JSON response from a role into (action, confidence, reasoning)."""
        # Strip markdown code fences if present
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(clean)
            action = str(data.get("action", "NEUTRAL")).upper()
            if action not in ("BUY", "SELL", "NEUTRAL", "VETO"):
                action = "NEUTRAL"
            confidence = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
            reasoning = str(data.get("reasoning", text[:200]))
            return action, confidence, reasoning
        except (json.JSONDecodeError, ValueError, TypeError):
            # Fallback: try to extract action from text
            upper = text.upper()
            if "BUY" in upper:
                action = "BUY"
            elif "SELL" in upper:
                action = "SELL"
            elif "VETO" in upper:
                action = "VETO"
            else:
                action = "NEUTRAL"
            return action, 0.3, text[:300]

    # ------------------------------------------------------------------
    # Internal: consensus
    # ------------------------------------------------------------------

    def _aggregate(self, predictions: list[RolePrediction]) -> dict[str, Any]:
        """Weighted vote across role predictions → consensus."""
        # Veto check first
        veto = next((p for p in predictions if p.action == "VETO"), None)
        if veto:
            return {
                "action": "NEUTRAL",
                "confidence": 0.0,
                "reasoning": f"VETOED by {veto.role}: {veto.reasoning}",
                "vetoed_by": veto.role,
            }

        scores: dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        counts: dict[str, int] = {"BUY": 0, "SELL": 0, "NEUTRAL": 0}

        for pred in predictions:
            weight = ROLE_WEIGHTS.get(pred.role, 1.0)
            action = pred.action if pred.action in scores else "NEUTRAL"
            scores[action] += pred.confidence * weight
            counts[action] += 1

        total_weight = sum(scores.values()) or 1.0
        best_action = max(scores, key=lambda a: scores[a])
        best_score = scores[best_action] / total_weight

        # Require min confidence threshold to act (protect capital)
        if best_score < 0.45:
            best_action = "NEUTRAL"
            best_score = 0.0

        # Require at least 2 roles agreeing
        if counts.get(best_action, 0) < 2 and best_action != "NEUTRAL":
            best_action = "NEUTRAL"
            best_score = 0.0

        parts = [f"{p.role}:{p.action}({p.confidence:.2f})" for p in predictions]
        reasoning = f"Consensus: {best_action} | " + " | ".join(parts)

        return {
            "action": best_action,
            "confidence": round(best_score, 4),
            "reasoning": reasoning,
            "vetoed_by": None,
        }

    # ------------------------------------------------------------------
    # Internal: DB storage
    # ------------------------------------------------------------------

    async def _store_predictions(
        self,
        exchange: str,
        symbol: str,
        horizon: str,
        predictions: list[RolePrediction],
        stats: dict[str, Any],
    ) -> list[int]:
        """Store all role predictions in pair_predictions table."""
        import asyncpg

        price_at_pred = float(stats.get("price", 0))

        conn = await asyncpg.connect(self.db_url, timeout=5)
        try:
            ids = []
            for pred in predictions:
                row = await conn.fetchrow(
                    """
                    INSERT INTO pair_predictions (
                        exchange, symbol, role, action, confidence, reasoning, horizon,
                        provider, model, tokens_in, tokens_out, latency_ms, cost_usd,
                        price_at_prediction
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    RETURNING id
                    """,
                    exchange,
                    symbol,
                    pred.role,
                    pred.action,
                    pred.confidence,
                    pred.reasoning[:2000],
                    horizon,
                    pred.provider,
                    pred.model,
                    pred.tokens_in,
                    pred.tokens_out,
                    pred.latency_ms,
                    pred.cost_usd,
                    price_at_pred,
                )
                ids.append(row["id"])
            return ids
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # Internal: cache
    # ------------------------------------------------------------------

    async def _get_cache(self, cache_key: str) -> MultiAgentResult | None:
        """Check prediction cache (5-minute TTL)."""
        import asyncpg

        try:
            conn = await asyncpg.connect(self.db_url, timeout=3)
            try:
                row = await conn.fetchrow(
                    """
                    SELECT predictions, consensus_action, consensus_confidence
                    FROM prediction_cache
                    WHERE cache_key = $1 AND expires_at > NOW()
                    """,
                    cache_key,
                )
                if not row:
                    return None

                preds = [RolePrediction(**p) for p in (row["predictions"] or [])]
                exchange, symbol, _ = cache_key.split(":", 2)
                return MultiAgentResult(
                    exchange=exchange,
                    symbol=symbol,
                    consensus_action=row["consensus_action"],
                    consensus_confidence=float(row["consensus_confidence"]),
                    predictions=preds,
                    from_cache=True,
                )
            finally:
                await conn.close()
        except Exception:
            return None

    async def _set_cache(self, cache_key: str, result: MultiAgentResult) -> None:
        """Store result in prediction cache."""
        import asyncpg

        expires = datetime.now(timezone.utc) + timedelta(seconds=self.CACHE_TTL_SECONDS)
        preds_json = json.dumps([p.to_dict() for p in result.predictions])

        conn = await asyncpg.connect(self.db_url, timeout=3)
        try:
            await conn.execute(
                """
                INSERT INTO prediction_cache (cache_key, predictions, consensus_action, consensus_confidence, expires_at)
                VALUES ($1, $2::jsonb, $3, $4, $5)
                ON CONFLICT (cache_key) DO UPDATE SET
                    predictions = EXCLUDED.predictions,
                    consensus_action = EXCLUDED.consensus_action,
                    consensus_confidence = EXCLUDED.consensus_confidence,
                    expires_at = EXCLUDED.expires_at,
                    created_at = NOW()
                """,
                cache_key,
                preds_json,
                result.consensus_action,
                result.consensus_confidence,
                expires,
            )
        finally:
            await conn.close()
