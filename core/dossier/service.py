"""Coin Dossier service — daily LLM-generated analysis per coin/pair.

Builds a coherent, evolving narrative for each trading pair:
- Stats snapshot (price, RSI, MACD, EMA trend, etc.)
- Retrospective review of previous prediction
- Technical analysis with LLM narrative
- New prediction / outlook

Usage:
    from core.dossier.service import DossierService

    svc = DossierService()
    entry = await svc.generate_entry("bitfinex", "BTCUSD")
    entries = await svc.get_history("bitfinex", "BTCUSD", days=30)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEBUG = os.environ.get("DOSSIER_DEBUG", "").lower() in ("1", "true", "yes")


def _debug(msg: str) -> None:
    if DEBUG:
        print(f"🔍 [Dossier] {msg}", flush=True)
    logger.debug(msg)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class DossierEntry:
    """A single dossier entry for one coin on one day."""

    id: int = 0
    exchange: str = ""
    symbol: str = ""
    entry_date: date = field(default_factory=date.today)

    # Stats snapshot
    price: float = 0.0
    change_24h: float = 0.0
    change_7d: float = 0.0
    volume_24h: float = 0.0
    rsi: float = 0.0
    macd_signal: str = "neutral"
    ema_trend: str = "flat"
    support_level: float = 0.0
    resistance_level: float = 0.0
    signal_score: float = 0.0

    # Narrative sections
    lore: str = ""
    stats_summary: str = ""
    tech_analysis: str = ""
    retrospective: str = ""
    prediction: str = ""
    full_narrative: str = ""

    # Prediction tracking
    predicted_direction: str = ""
    predicted_target: float = 0.0
    predicted_timeframe: str = "24h"
    prediction_correct: bool | None = None

    # Metadata
    model_used: str = ""
    tokens_used: int = 0
    generation_time_ms: int = 0
    created_at: datetime | None = None


@dataclass
class CoinProfile:
    """Static/semi-static coin profile."""

    symbol: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    founded_year: int | None = None
    notable_events: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Well-known coin profiles (used when DB profile is empty)
# ---------------------------------------------------------------------------

COIN_LORE: dict[str, dict[str, str]] = {
    "BTCUSD": {
        "name": "Bitcoin",
        "category": "L1",
        "lore": (
            "Bitcoin (BTC) is the first cryptocurrency, created in 2009 by "
            "Satoshi Nakamoto. It serves as a decentralized store of value and "
            "digital gold, with market dominance typically above 40%. Key events "
            "include the 2017 bull run, 2020 institutional adoption wave, and "
            "2024 spot ETF approvals. Supply capped at 21M coins, with halving "
            "events roughly every 4 years."
        ),
    },
    "ETHUSD": {
        "name": "Ethereum",
        "category": "L1 / Smart Contract Platform",
        "lore": (
            "Ethereum (ETH) is the leading smart contract platform, launched in "
            "2015 by Vitalik Buterin. Transitioned to Proof-of-Stake via The "
            "Merge in September 2022. Powers the majority of DeFi, NFTs, and "
            "Layer-2 ecosystems. Key events include the DAO hack (2016), DeFi "
            "Summer (2020), and EIP-1559 burn mechanism."
        ),
    },
    "SOLUSD": {
        "name": "Solana",
        "category": "L1 / High Performance",
        "lore": (
            "Solana (SOL) is a high-throughput Layer-1 blockchain known for fast "
            "transactions and low fees. Founded by Anatoly Yakovenko in 2020. "
            "Survived the FTX collapse in 2022 and made a strong comeback in "
            "2023-2024. Popular for DeFi, NFTs, and meme coins."
        ),
    },
    "XRPUSD": {
        "name": "XRP",
        "category": "Payments",
        "lore": (
            "XRP is the native token of the XRP Ledger, created by Ripple Labs "
            "for cross-border payments. Notable for the SEC lawsuit (2020-2023) "
            "and partial victory. One of the oldest crypto assets, with strong "
            "institutional payment network adoption."
        ),
    },
    "DOGEUSD": {
        "name": "Dogecoin",
        "category": "Meme / Payments",
        "lore": (
            "Dogecoin (DOGE) started as a joke in 2013 based on the Shiba Inu "
            "meme. Gained massive popularity through Elon Musk endorsements and "
            "Reddit communities. Despite meme origins, it has one of the most "
            "active transaction networks and loyal communities."
        ),
    },
}

# ---------------------------------------------------------------------------
# Default model setup
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_HOST = "http://localhost:11434"


class DossierService:
    """Generates and manages daily coin dossier entries."""

    # Prompt for generating the full dossier narrative
    DOSSIER_SYSTEM_PROMPT = """You are a senior cryptocurrency analyst writing a daily briefing dossier.

Your dossiers are:
- Professional but engaging — like a Bloomberg analyst note
- Data-driven — always reference specific numbers (price, RSI, volume, etc.)
- Historically aware — you reference your previous analysis and whether it played out
- Honest about uncertainty and past mistakes
- Forward-looking with a clear directional call

Structure your response EXACTLY as follows (use these exact headers):

## STATS SUMMARY
(2-3 sentences summarizing current metrics — price, 24h change, RSI, volume, trend)

## TECHNICAL ANALYSIS
(3-5 paragraphs on the current technical setup — indicators, trend, key levels, volume analysis)

## RETROSPECTIVE
(2-3 paragraphs reviewing yesterday's prediction — was it correct? What happened differently? Why?)

## PREDICTION
(2-3 paragraphs with your new outlook — direction, target, confidence level, key triggers)

## DIRECTION
(Exactly one word: UP, DOWN, or SIDEWAYS)

## TARGET
(Exactly one number: your price target for the next 24h, e.g. 98500.00)"""

    def __init__(
        self,
        db_url: str | None = None,
        model: str | None = None,
        host: str | None = None,
    ):
        self.db_url = db_url or os.environ.get(
            "DATABASE_URL",
            "postgresql://cryptotrader:cryptotrader@localhost:5432/cryptotrader",
        )
        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        self.host = host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)
        self._auth_user = os.environ.get("OLLAMA_USER", "cryptotrader")
        self._auth: httpx.BasicAuth | None = (
            httpx.BasicAuth(username=self._auth_user, password="") if self._auth_user else None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_entry(
        self,
        exchange: str,
        symbol: str,
        entry_date: date | None = None,
    ) -> DossierEntry:
        """Generate a dossier entry for a coin on a given date.

        Fetches current stats, retrieves previous entries for context,
        calls the LLM, and stores the result.
        """
        target_date = entry_date or date.today()
        _debug(f"📝 Generating dossier for {exchange}:{symbol} on {target_date}")

        # 1. Gather current stats from candle data
        stats = await self._gather_stats(exchange, symbol)
        _debug(f"📊 Stats gathered: price={stats.get('price')}, rsi={stats.get('rsi')}")

        # 2. Get previous entries for context
        prev_entries = await self._get_recent_entries(exchange, symbol, days=7)
        _debug(f"📚 Found {len(prev_entries)} previous entries")

        # 3. Get coin profile / lore
        lore = self._get_coin_lore(symbol)

        # 4. Build prompt and query LLM
        prompt = self._build_dossier_prompt(exchange, symbol, stats, prev_entries, lore)

        start_ms = time.monotonic_ns() // 1_000_000
        llm_response = await self._query_llm(prompt)
        elapsed_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        # 5. Parse LLM response into structured entry
        entry = self._parse_llm_response(llm_response, exchange, symbol, target_date, stats)
        entry.lore = lore
        entry.model_used = self.model
        entry.tokens_used = llm_response.get("eval_count", 0)
        entry.generation_time_ms = int(elapsed_ms)

        _debug(f"✅ Generated dossier: {entry.predicted_direction} → ${entry.predicted_target}")

        # 6. Evaluate previous prediction (if any)
        if prev_entries:
            await self._evaluate_previous_prediction(prev_entries[0], stats)

        # 7. Store in database
        entry = await self._store_entry(entry)
        _debug(f"💾 Stored entry id={entry.id}")

        return entry

    async def generate_all(self, exchange: str = "bitfinex") -> list[DossierEntry]:
        """Generate dossier entries for all available pairs on an exchange."""
        symbols = await self._get_available_symbols(exchange)
        _debug(f"🔄 Generating dossiers for {len(symbols)} symbols on {exchange}")

        entries = []
        for symbol in symbols:
            try:
                entry = await self.generate_entry(exchange, symbol)
                entries.append(entry)
            except Exception as e:
                logger.error(f"Failed to generate dossier for {exchange}:{symbol}: {e}")
                _debug(f"❌ Failed: {exchange}:{symbol} — {e}")

        _debug(f"✅ Generated {len(entries)}/{len(symbols)} dossiers")
        return entries

    async def get_entry(
        self,
        exchange: str,
        symbol: str,
        entry_date: date | None = None,
    ) -> DossierEntry | None:
        """Get a specific dossier entry."""
        target_date = entry_date or date.today()
        entries = await self._get_recent_entries(exchange, symbol, days=1, from_date=target_date)
        return entries[0] if entries else None

    async def get_history(
        self,
        exchange: str,
        symbol: str,
        days: int = 30,
    ) -> list[DossierEntry]:
        """Get dossier history for a coin."""
        return await self._get_recent_entries(exchange, symbol, days=days)

    async def get_all_latest(self, exchange: str = "bitfinex") -> list[DossierEntry]:
        """Get the latest dossier entry for all coins on an exchange."""
        import asyncpg

        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (symbol) *
                    FROM coin_dossier_entries
                    WHERE exchange = $1
                    ORDER BY symbol, entry_date DESC
                    """,
                    exchange,
                )
                return [self._row_to_entry(r) for r in rows]
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to get latest dossiers: {e}")
            return []

    async def get_available_symbols(self, exchange: str = "bitfinex") -> list[str]:
        """Get all symbols that have dossier entries."""
        import asyncpg

        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT symbol
                    FROM coin_dossier_entries
                    WHERE exchange = $1
                    ORDER BY symbol
                    """,
                    exchange,
                )
                return [r["symbol"] for r in rows]
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to get dossier symbols: {e}")
            # Fall back to candle data symbols
            return await self._get_available_symbols(exchange)

    # ------------------------------------------------------------------
    # Internal: data gathering
    # ------------------------------------------------------------------

    async def _gather_stats(self, exchange: str, symbol: str) -> dict[str, Any]:
        """Gather current stats from the candles table."""
        import asyncpg

        conn = await asyncpg.connect(self.db_url)
        try:
            # Get last 200 hourly candles for indicator calculation
            rows = await conn.fetch(
                """
                SELECT open_time, open, high, low, close, volume
                FROM candles
                WHERE exchange = $1 AND symbol = $2 AND timeframe = '1h'
                ORDER BY open_time DESC
                LIMIT 200
                """,
                exchange,
                symbol,
            )

            if not rows:
                return {"price": 0, "error": "No candle data available"}

            rows = list(reversed(rows))  # oldest first
            closes = [float(r["close"]) for r in rows]
            volumes = [float(r["volume"]) for r in rows]
            highs = [float(r["high"]) for r in rows]
            lows = [float(r["low"]) for r in rows]

            stats: dict[str, Any] = {
                "price": closes[-1],
                "candle_count": len(closes),
            }

            # 24h change
            if len(closes) >= 24:
                stats["change_24h"] = round((closes[-1] - closes[-24]) / closes[-24] * 100, 2)
            # 7d change
            if len(closes) >= 168:
                stats["change_7d"] = round((closes[-1] - closes[-168]) / closes[-168] * 100, 2)

            # 24h volume
            stats["volume_24h"] = round(sum(volumes[-24:]), 2) if len(volumes) >= 24 else round(sum(volumes), 2)

            # RSI (14 period)
            if len(closes) >= 15:
                gains = []
                losses = []
                for i in range(1, len(closes)):
                    delta = closes[i] - closes[i - 1]
                    gains.append(max(0, delta))
                    losses.append(max(0, -delta))

                avg_gain = sum(gains[-14:]) / 14
                avg_loss = sum(losses[-14:]) / 14
                if avg_loss > 0:
                    rs = avg_gain / avg_loss
                    stats["rsi"] = round(100 - (100 / (1 + rs)), 1)
                else:
                    stats["rsi"] = 100.0

            # EMA calculations
            def ema(data: list[float], period: int) -> float:
                if len(data) < period:
                    return data[-1]
                mult = 2 / (period + 1)
                val = sum(data[:period]) / period
                for p in data[period:]:
                    val = (p * mult) + (val * (1 - mult))
                return val

            ema_9 = ema(closes, 9)
            ema_21 = ema(closes, 21)
            ema_50 = ema(closes, 50) if len(closes) >= 50 else None

            stats["ema_9"] = round(ema_9, 2)
            stats["ema_21"] = round(ema_21, 2)
            if ema_50:
                stats["ema_50"] = round(ema_50, 2)

            # EMA trend
            if ema_9 > ema_21:
                stats["ema_trend"] = "up"
            elif ema_9 < ema_21:
                stats["ema_trend"] = "down"
            else:
                stats["ema_trend"] = "flat"

            # MACD
            if len(closes) >= 26:
                ema_12 = ema(closes, 12)
                ema_26 = ema(closes, 26)
                macd = ema_12 - ema_26
                stats["macd"] = round(macd, 4)
                stats["macd_signal"] = "bullish" if macd > 0 else "bearish"

            # Support & resistance (simple: recent 24h low/high)
            if len(lows) >= 24:
                stats["support_level"] = round(min(lows[-24:]), 2)
            if len(highs) >= 24:
                stats["resistance_level"] = round(max(highs[-24:]), 2)

            # Volume average ratio
            if len(volumes) >= 48:
                avg_vol = sum(volumes[-48:-24]) / 24
                cur_vol = sum(volumes[-24:]) / 24
                stats["volume_ratio"] = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            return stats

        finally:
            await conn.close()

    async def _get_available_symbols(self, exchange: str) -> list[str]:
        """Get available symbols from candle data."""
        import asyncpg

        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT symbol
                FROM candles
                WHERE exchange = $1 AND timeframe = '1h'
                ORDER BY symbol
                """,
                exchange,
            )
            return [r["symbol"] for r in rows]
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # Internal: previous entries
    # ------------------------------------------------------------------

    async def _get_recent_entries(
        self,
        exchange: str,
        symbol: str,
        days: int = 7,
        from_date: date | None = None,
    ) -> list[DossierEntry]:
        """Get recent dossier entries for context."""
        import asyncpg

        target = from_date or date.today()
        since = target - timedelta(days=days)

        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM coin_dossier_entries
                    WHERE exchange = $1
                      AND symbol = $2
                      AND entry_date BETWEEN $3 AND $4
                    ORDER BY entry_date DESC
                    """,
                    exchange,
                    symbol,
                    since,
                    target,
                )
                return [self._row_to_entry(r) for r in rows]
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to get recent entries: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal: coin lore
    # ------------------------------------------------------------------

    def _get_coin_lore(self, symbol: str) -> str:
        """Get background lore for a coin."""
        known = COIN_LORE.get(symbol, {})
        if known.get("lore"):
            return known["lore"]
        # Generic fallback
        return f"{symbol} is a cryptocurrency trading pair tracked by the system."

    # ------------------------------------------------------------------
    # Internal: LLM interaction
    # ------------------------------------------------------------------

    def _build_dossier_prompt(
        self,
        exchange: str,
        symbol: str,
        stats: dict[str, Any],
        prev_entries: list[DossierEntry],
        lore: str,
    ) -> str:
        """Build the comprehensive dossier prompt."""
        # Format current stats
        stats_block = f"""Current metrics for {symbol} on {exchange}:
- Price: ${stats.get("price", 0):,.2f}
- 24h Change: {stats.get("change_24h", 0):+.2f}%
- 7d Change: {stats.get("change_7d", "N/A")}{"%" if isinstance(stats.get("change_7d"), (int, float)) else ""}
- 24h Volume: ${stats.get("volume_24h", 0):,.0f}
- RSI (14): {stats.get("rsi", "N/A")}
- EMA(9): ${stats.get("ema_9", 0):,.2f} | EMA(21): ${stats.get("ema_21", 0):,.2f}
- EMA Trend: {stats.get("ema_trend", "N/A")}
- MACD: {stats.get("macd", "N/A")} ({stats.get("macd_signal", "N/A")})
- Support: ${stats.get("support_level", 0):,.2f}
- Resistance: ${stats.get("resistance_level", 0):,.2f}
- Volume Ratio (vs avg): {stats.get("volume_ratio", "N/A")}x"""

        # Format previous entries context
        history_block = ""
        if prev_entries:
            history_block = "\n\n=== PREVIOUS DOSSIER ENTRIES ===\n"
            for entry in prev_entries[:5]:  # Last 5 entries max
                correct_str = ""
                if entry.prediction_correct is True:
                    correct_str = " ✅ (prediction was CORRECT)"
                elif entry.prediction_correct is False:
                    correct_str = " ❌ (prediction was WRONG)"

                history_block += f"""
--- {entry.entry_date} ---
Price: ${entry.price:,.2f}
Prediction: {entry.predicted_direction} → ${entry.predicted_target:,.2f}{correct_str}
Summary: {entry.stats_summary[:200]}
Analysis excerpt: {entry.tech_analysis[:300]}
Prediction text: {entry.prediction[:200]}
"""
        else:
            history_block = "\n\n(This is the FIRST dossier entry for this coin — no prior history available.)\n"

        prompt = f"""=== COIN BACKGROUND ===
{lore}

=== CURRENT DATA ({date.today()}) ===
{stats_block}
{history_block}

Write the daily dossier entry for {symbol}. Follow the format exactly.
Be specific with numbers. Reference previous predictions if available.
If this is the first entry, skip the retrospective section and focus on laying a solid analytical foundation."""

        return prompt

    async def _query_llm(self, prompt: str, max_tokens: int = 2000) -> dict:
        """Query Ollama for dossier generation."""
        url = f"{self.host}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": self.DOSSIER_SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            },
        }

        _debug(f"🤖 Querying {self.model} at {self.host}")

        async with httpx.AsyncClient(auth=self._auth) as client:
            response = await client.post(
                url,
                json=payload,
                timeout=120.0,  # Dossier generation can take time
            )
            response.raise_for_status()
            return response.json()

    def _parse_llm_response(
        self,
        response: dict,
        exchange: str,
        symbol: str,
        entry_date: date,
        stats: dict[str, Any],
    ) -> DossierEntry:
        """Parse the LLM response into a structured DossierEntry."""
        text = response.get("response", "")

        # Extract sections by headers
        sections = {
            "stats_summary": "",
            "tech_analysis": "",
            "retrospective": "",
            "prediction": "",
        }

        current_section = ""
        current_lines: list[str] = []

        for line in text.split("\n"):
            stripped = line.strip().upper()
            if "STATS SUMMARY" in stripped and stripped.startswith("#"):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = "stats_summary"
                current_lines = []
            elif "TECHNICAL ANALYSIS" in stripped and stripped.startswith("#"):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = "tech_analysis"
                current_lines = []
            elif "RETROSPECTIVE" in stripped and stripped.startswith("#"):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = "retrospective"
                current_lines = []
            elif (
                "PREDICTION" in stripped
                and "DIRECTION" not in stripped
                and "TARGET" not in stripped
                and stripped.startswith("#")
            ):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = "prediction"
                current_lines = []
            elif "DIRECTION" in stripped and stripped.startswith("#"):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = "direction"
                current_lines = []
            elif "TARGET" in stripped and stripped.startswith("#"):
                if current_section:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = "target"
                current_lines = []
            else:
                current_lines.append(line)

        # Capture last section
        if current_section:
            sections[current_section] = "\n".join(current_lines).strip()

        # Extract direction
        direction_text = sections.get("direction", "").strip().upper()
        direction = "sideways"
        if "UP" in direction_text:
            direction = "up"
        elif "DOWN" in direction_text:
            direction = "down"

        # Extract target price
        target_text = sections.get("target", "").strip()
        target_price = 0.0
        for token in target_text.replace("$", "").replace(",", "").split():
            try:
                target_price = float(token)
                break
            except ValueError:
                continue
        if target_price == 0:
            target_price = stats.get("price", 0)

        return DossierEntry(
            exchange=exchange,
            symbol=symbol,
            entry_date=entry_date,
            price=stats.get("price", 0),
            change_24h=stats.get("change_24h", 0),
            change_7d=stats.get("change_7d", 0),
            volume_24h=stats.get("volume_24h", 0),
            rsi=stats.get("rsi", 0),
            macd_signal=stats.get("macd_signal", "neutral"),
            ema_trend=stats.get("ema_trend", "flat"),
            support_level=stats.get("support_level", 0),
            resistance_level=stats.get("resistance_level", 0),
            signal_score=0,  # TODO: integrate with signal score
            lore="",  # Set by caller
            stats_summary=sections.get("stats_summary", ""),
            tech_analysis=sections.get("tech_analysis", ""),
            retrospective=sections.get("retrospective", ""),
            prediction=sections.get("prediction", ""),
            full_narrative=text,
            predicted_direction=direction,
            predicted_target=target_price,
            predicted_timeframe="24h",
        )

    # ------------------------------------------------------------------
    # Internal: prediction evaluation
    # ------------------------------------------------------------------

    async def _evaluate_previous_prediction(
        self,
        prev_entry: DossierEntry,
        current_stats: dict[str, Any],
    ) -> None:
        """Evaluate if the previous prediction was correct."""
        if not prev_entry.predicted_direction or not prev_entry.price:
            return

        current_price = current_stats.get("price", 0)
        if not current_price:
            return

        price_change_pct = (current_price - prev_entry.price) / prev_entry.price * 100

        correct = False
        if prev_entry.predicted_direction == "up" and price_change_pct > 0.5:
            correct = True
        elif prev_entry.predicted_direction == "down" and price_change_pct < -0.5:
            correct = True
        elif prev_entry.predicted_direction == "sideways" and abs(price_change_pct) <= 2.0:
            correct = True

        _debug(
            f"📈 Previous prediction: {prev_entry.predicted_direction}, "
            f"actual change: {price_change_pct:+.2f}%, correct: {correct}"
        )

        # Update in database
        import asyncpg

        try:
            conn = await asyncpg.connect(self.db_url)
            try:
                await conn.execute(
                    """
                    UPDATE coin_dossier_entries
                    SET prediction_correct = $1
                    WHERE id = $2
                    """,
                    correct,
                    prev_entry.id,
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to update prediction status: {e}")

    # ------------------------------------------------------------------
    # Internal: storage
    # ------------------------------------------------------------------

    async def _store_entry(self, entry: DossierEntry) -> DossierEntry:
        """Store or update a dossier entry in the database."""
        import asyncpg

        conn = await asyncpg.connect(self.db_url)
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO coin_dossier_entries (
                    exchange, symbol, entry_date,
                    price, change_24h, change_7d, volume_24h,
                    rsi, macd_signal, ema_trend,
                    support_level, resistance_level, signal_score,
                    lore, stats_summary, tech_analysis,
                    retrospective, prediction, full_narrative,
                    predicted_direction, predicted_target, predicted_timeframe,
                    model_used, tokens_used, generation_time_ms
                ) VALUES (
                    $1, $2, $3,
                    $4, $5, $6, $7,
                    $8, $9, $10,
                    $11, $12, $13,
                    $14, $15, $16,
                    $17, $18, $19,
                    $20, $21, $22,
                    $23, $24, $25
                )
                ON CONFLICT (exchange, symbol, entry_date)
                DO UPDATE SET
                    price = EXCLUDED.price,
                    change_24h = EXCLUDED.change_24h,
                    change_7d = EXCLUDED.change_7d,
                    volume_24h = EXCLUDED.volume_24h,
                    rsi = EXCLUDED.rsi,
                    macd_signal = EXCLUDED.macd_signal,
                    ema_trend = EXCLUDED.ema_trend,
                    support_level = EXCLUDED.support_level,
                    resistance_level = EXCLUDED.resistance_level,
                    signal_score = EXCLUDED.signal_score,
                    lore = EXCLUDED.lore,
                    stats_summary = EXCLUDED.stats_summary,
                    tech_analysis = EXCLUDED.tech_analysis,
                    retrospective = EXCLUDED.retrospective,
                    prediction = EXCLUDED.prediction,
                    full_narrative = EXCLUDED.full_narrative,
                    predicted_direction = EXCLUDED.predicted_direction,
                    predicted_target = EXCLUDED.predicted_target,
                    predicted_timeframe = EXCLUDED.predicted_timeframe,
                    model_used = EXCLUDED.model_used,
                    tokens_used = EXCLUDED.tokens_used,
                    generation_time_ms = EXCLUDED.generation_time_ms,
                    created_at = NOW()
                RETURNING id
                """,
                entry.exchange,
                entry.symbol,
                entry.entry_date,
                entry.price,
                entry.change_24h,
                entry.change_7d,
                entry.volume_24h,
                entry.rsi,
                entry.macd_signal,
                entry.ema_trend,
                entry.support_level,
                entry.resistance_level,
                entry.signal_score,
                entry.lore,
                entry.stats_summary,
                entry.tech_analysis,
                entry.retrospective,
                entry.prediction,
                entry.full_narrative,
                entry.predicted_direction,
                entry.predicted_target,
                entry.predicted_timeframe,
                entry.model_used,
                entry.tokens_used,
                entry.generation_time_ms,
            )
            entry.id = row["id"]
            return entry
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: Any) -> DossierEntry:
        """Convert a database row to a DossierEntry."""
        return DossierEntry(
            id=row["id"],
            exchange=row["exchange"],
            symbol=row["symbol"],
            entry_date=row["entry_date"],
            price=float(row["price"] or 0),
            change_24h=float(row["change_24h"] or 0),
            change_7d=float(row["change_7d"] or 0),
            volume_24h=float(row["volume_24h"] or 0),
            rsi=float(row["rsi"] or 0),
            macd_signal=row["macd_signal"] or "neutral",
            ema_trend=row["ema_trend"] or "flat",
            support_level=float(row["support_level"] or 0),
            resistance_level=float(row["resistance_level"] or 0),
            signal_score=float(row["signal_score"] or 0),
            lore=row["lore"] or "",
            stats_summary=row["stats_summary"] or "",
            tech_analysis=row["tech_analysis"] or "",
            retrospective=row["retrospective"] or "",
            prediction=row["prediction"] or "",
            full_narrative=row["full_narrative"] or "",
            predicted_direction=row["predicted_direction"] or "",
            predicted_target=float(row["predicted_target"] or 0),
            predicted_timeframe=row["predicted_timeframe"] or "24h",
            prediction_correct=row["prediction_correct"],
            model_used=row["model_used"] or "",
            tokens_used=row["tokens_used"] or 0,
            generation_time_ms=row["generation_time_ms"] or 0,
            created_at=row["created_at"],
        )
