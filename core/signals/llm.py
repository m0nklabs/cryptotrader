"""Guardian LLM integration for natural language trading analysis.

Provides AI-powered explanations and insights for trading decisions.
Uses the local Guardian proxy (llama_cpp_guardian) via the OpenAI-compatible
/v1/chat/completions endpoint for privacy and cost efficiency.

Usage:
    from core.signals.llm import GuardianAnalyst, get_llm_analysis

    # Quick analysis
    explanation = await get_llm_analysis(analysis, question="should I buy?")

    # Full analyst
    analyst = GuardianAnalyst(model="GLM-4.7-Flash")
    response = await analyst.explain(analysis)

# Backward-compat alias:
#   OllamaAnalyst = GuardianAnalyst  (defined at module bottom)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from core.signals.reasoning import TechnicalAnalysis, Recommendation

logger = logging.getLogger(__name__)


class GuardianUnauthenticated(Exception):
    """Raised when Guardian requires an API key but none is configured."""

    pass


@dataclass
class LLMResponse:
    """Response from LLM analysis."""

    summary: str
    detailed_explanation: str
    risk_assessment: str
    confidence_note: str
    model_used: str
    tokens_used: int = 0


class GuardianAnalyst:
    """Guardian-proxy-based trading analyst for natural language explanations.

    Uses the local llama_cpp_guardian proxy at /v1/chat/completions with
    Bearer token authentication (GUARDIAN_API_KEY env var).
    """

    DEFAULT_MODEL = "GLM-4.7-Flash"
    DEFAULT_HOST = "http://localhost:11434"

    # System prompt for trading analysis
    SYSTEM_PROMPT = """You are a professional cryptocurrency trading analyst.
Your job is to explain technical analysis in clear, actionable terms.

Guidelines:
- Be concise but thorough
- Explain the reasoning, not just the conclusion
- Always mention key risks
- Use percentages and specific numbers when available
- Be honest about uncertainty
- Never guarantee profits

Format your response as:
SUMMARY: (1-2 sentences)
ANALYSIS: (detailed explanation)
RISKS: (key risks to consider)
CONFIDENCE: (your confidence in the analysis)"""

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: float = 60.0,
    ):
        """Initialize Guardian analyst.

        Args:
            model: Model name served by Guardian (default: GLM-4.7-Flash)
            host: Guardian proxy host (default: http://localhost:11434)
            timeout: Request timeout in seconds

        Environment variables:
            GUARDIAN_API_KEY: Bearer token for Guardian proxy (REQUIRED for /v1/models)
            GUARDIAN_HOST: Guardian proxy URL
            GUARDIAN_MODEL: Override default model

        Raises:
            GuardianUnauthenticated: If GUARDIAN_API_KEY is absent and
                is_available() is called — short-circuits instead of
                hammering the proxy without auth.
        """
        self.model = model or os.environ.get("GUARDIAN_MODEL", self.DEFAULT_MODEL)
        self.host = host or os.environ.get("GUARDIAN_HOST", self.DEFAULT_HOST)
        self.timeout = timeout
        api_key = os.environ.get("GUARDIAN_API_KEY", "")
        self._api_key = api_key  # stored for short-circuit checks
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    async def explain(
        self,
        analysis: TechnicalAnalysis,
        question: str | None = None,
    ) -> LLMResponse:
        """Generate natural language explanation of analysis.

        Args:
            analysis: Technical analysis to explain
            question: Optional specific question (e.g., "should I buy now?")

        Returns:
            LLM response with explanation
        """
        prompt = self._build_prompt(analysis, question)

        try:
            response = await self._query_guardian(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.exception(f"Guardian query failed: {e}")
            return self._fallback_response(analysis, str(e))

    async def summarize(self, analysis: TechnicalAnalysis) -> str:
        """Get a brief summary of the analysis.

        Args:
            analysis: Technical analysis to summarize

        Returns:
            Brief summary string
        """
        prompt = f"""Summarize this trading analysis in ONE sentence:

Symbol: {analysis.symbol}
Recommendation: {analysis.recommendation.value}
Confidence: {analysis.confidence}%
Key factors: {", ".join(analysis.reasoning[:3])}

One sentence summary:"""

        try:
            response = await self._query_guardian(prompt, max_tokens=100)
            return response.get("response", "").strip()
        except Exception as e:
            logger.warning(f"Summary failed: {e}")
            return f"{analysis.symbol}: {analysis.recommendation.value} with {analysis.confidence}% confidence"

    async def answer_question(
        self,
        analysis: TechnicalAnalysis,
        question: str,
    ) -> str:
        """Answer a specific question about the analysis.

        Args:
            analysis: Technical analysis context
            question: User's question

        Returns:
            Answer string
        """
        prompt = f"""Based on this technical analysis, answer the question.

=== ANALYSIS ===
Symbol: {analysis.symbol}
Current Price: ${analysis.current_price:,.2f}
Recommendation: {analysis.recommendation.value}
Confidence: {analysis.confidence}%

Bullish factors:
{chr(10).join(f"- {f}" for f in analysis.bullish_factors)}

Bearish factors:
{chr(10).join(f"- {f}" for f in analysis.bearish_factors)}

Support levels: {", ".join(f"${s:,.0f}" for s in analysis.support_levels)}
Resistance levels: {", ".join(f"${r:,.0f}" for r in analysis.resistance_levels)}

{f"Suggested entry: ${analysis.suggested_entry:,.2f}" if analysis.suggested_entry else ""}
{f"Suggested stop: ${analysis.suggested_stop:,.2f}" if analysis.suggested_stop else ""}
{f"Risk/Reward: {analysis.risk_reward_ratio:.1f}:1" if analysis.risk_reward_ratio else ""}

=== QUESTION ===
{question}

=== ANSWER ==="""

        try:
            response = await self._query_guardian(prompt, max_tokens=500)
            return response.get("response", "").strip()
        except Exception as e:
            logger.warning(f"Question answering failed: {e}")
            return f"Unable to answer: {e}"

    def _build_prompt(
        self,
        analysis: TechnicalAnalysis,
        question: str | None = None,
    ) -> str:
        """Build the prompt for LLM analysis."""
        # Format indicators
        indicators_str = ""
        if analysis.indicators:
            ind = analysis.indicators
            indicators_str = f"""
Indicators:
- RSI: {ind.get("rsi", "N/A"):.1f}
- MACD: {ind.get("macd", "N/A"):.4f} (Signal: {ind.get("macd_signal", "N/A"):.4f})
- EMA20: ${ind.get("ema_20", 0):,.2f}
- EMA50: ${ind.get("ema_50", 0):,.2f}
- EMA200: ${ind.get("ema_200", 0):,.2f}
- ATR: {ind.get("atr_percent", 0):.2f}%
- Volume ratio: {ind.get("volume_ratio", 1):.1f}x average"""

        # Build main prompt
        prompt = f"""Analyze this trading setup and provide your assessment:

=== TECHNICAL ANALYSIS ===
Symbol: {analysis.symbol}
Timeframe: {analysis.timeframe}
Current Price: ${analysis.current_price:,.2f}
{indicators_str}

=== RULE-BASED RECOMMENDATION ===
Recommendation: {analysis.recommendation.value}
Confidence: {analysis.confidence}%

Bullish factors ({len(analysis.bullish_factors)}):
{chr(10).join(f"+ {f}" for f in analysis.bullish_factors)}

Bearish factors ({len(analysis.bearish_factors)}):
{chr(10).join(f"- {f}" for f in analysis.bearish_factors)}

Key levels:
- Support: {", ".join(f"${s:,.0f}" for s in analysis.support_levels) or "None identified"}
- Resistance: {", ".join(f"${r:,.0f}" for r in analysis.resistance_levels) or "None identified"}

Trade suggestion:
- Entry: {f"${analysis.suggested_entry:,.2f}" if analysis.suggested_entry else "N/A"}
- Stop loss: {f"${analysis.suggested_stop:,.2f}" if analysis.suggested_stop else "N/A"}
- Target: {f"${analysis.suggested_target:,.2f}" if analysis.suggested_target else "N/A"}
- Risk/Reward: {f"{analysis.risk_reward_ratio:.1f}:1" if analysis.risk_reward_ratio else "N/A"}

"""
        if question:
            prompt += f"""
=== USER QUESTION ===
{question}

Please address this question specifically in your analysis.
"""

        prompt += """
=== YOUR ANALYSIS ===
Provide your professional assessment following the format:
SUMMARY: (1-2 sentences)
ANALYSIS: (detailed explanation)
RISKS: (key risks to consider)
CONFIDENCE: (your confidence in the analysis)"""

        return prompt

    async def _fetch_model_ids(self) -> list[str]:
        """Fetch Guardian model ids with a single authenticated request."""
        if not self._api_key:
            raise GuardianUnauthenticated(
                "GUARDIAN_API_KEY is not set. " "Set the env var or skip Guardian LLM features."
            )

        async with httpx.AsyncClient(headers=self._headers) as client:
            response = await client.get(f"{self.host}/v1/models", timeout=5.0)
            response.raise_for_status()
            data = response.json()
        return [model["id"] for model in data.get("data", [])]

    async def get_models_status(self) -> tuple[bool, list[str]]:
        """Fetch Guardian availability and model ids in a single request."""
        try:
            return True, await self._fetch_model_ids()
        except GuardianUnauthenticated:
            raise
        except Exception as e:
            logger.warning(f"Failed to fetch Guardian models: {e}")
            return False, []

    async def _query_guardian(
        self,
        prompt: str,
        max_tokens: int = 1000,
    ) -> dict:
        """Query Guardian proxy via OpenAI-compatible /v1/chat/completions.

        Raises:
            GuardianUnauthenticated: If GUARDIAN_API_KEY is not set.

        Returns a dict with a "response" key containing the text, and
        "eval_count" with the token count — matching the shape callers expect.
        """
        if not self._api_key:
            raise GuardianUnauthenticated(
                "GUARDIAN_API_KEY is not set. " "Cannot query Guardian without authentication."
            )

        url = f"{self.host}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": False,
        }

        async with httpx.AsyncClient(headers=self._headers) as client:
            response = await client.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        # Normalise to the shape callers expect
        text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        return {"response": text, "eval_count": tokens}

    def _parse_response(self, response: dict) -> LLMResponse:
        """Parse Ollama response into structured format."""
        text = response.get("response", "")

        # Try to extract sections
        summary = ""
        analysis = ""
        risks = ""
        confidence = ""

        sections = text.split("\n")
        current_section = ""
        current_content = []

        for line in sections:
            line_upper = line.upper().strip()
            if line_upper.startswith("SUMMARY:"):
                if current_section and current_content:
                    if current_section == "SUMMARY":
                        summary = " ".join(current_content)
                    elif current_section == "ANALYSIS":
                        analysis = " ".join(current_content)
                    elif current_section == "RISKS":
                        risks = " ".join(current_content)
                    elif current_section == "CONFIDENCE":
                        confidence = " ".join(current_content)
                current_section = "SUMMARY"
                current_content = [line.split(":", 1)[1].strip()] if ":" in line else []
            elif line_upper.startswith("ANALYSIS:"):
                if current_section and current_content:
                    if current_section == "SUMMARY":
                        summary = " ".join(current_content)
                current_section = "ANALYSIS"
                current_content = [line.split(":", 1)[1].strip()] if ":" in line else []
            elif line_upper.startswith("RISKS:") or line_upper.startswith("RISK:"):
                if current_section and current_content:
                    if current_section == "ANALYSIS":
                        analysis = " ".join(current_content)
                current_section = "RISKS"
                current_content = [line.split(":", 1)[1].strip()] if ":" in line else []
            elif line_upper.startswith("CONFIDENCE:"):
                if current_section and current_content:
                    if current_section == "RISKS":
                        risks = " ".join(current_content)
                current_section = "CONFIDENCE"
                current_content = [line.split(":", 1)[1].strip()] if ":" in line else []
            elif current_section:
                current_content.append(line.strip())

        # Capture last section
        if current_section and current_content:
            if current_section == "SUMMARY":
                summary = " ".join(current_content)
            elif current_section == "ANALYSIS":
                analysis = " ".join(current_content)
            elif current_section == "RISKS":
                risks = " ".join(current_content)
            elif current_section == "CONFIDENCE":
                confidence = " ".join(current_content)

        # Fallback if parsing failed
        if not summary and not analysis:
            summary = text[:200] + "..." if len(text) > 200 else text
            analysis = text

        return LLMResponse(
            summary=summary.strip(),
            detailed_explanation=analysis.strip(),
            risk_assessment=risks.strip(),
            confidence_note=confidence.strip(),
            model_used=self.model,
            tokens_used=response.get("eval_count", 0),
        )

    def _fallback_response(self, analysis: TechnicalAnalysis, error: str) -> LLMResponse:
        """Generate fallback response when LLM fails."""
        # Generate rule-based summary
        rec = analysis.recommendation.value
        conf = analysis.confidence

        if analysis.recommendation in (Recommendation.STRONG_BUY, Recommendation.BUY):
            summary = f"{analysis.symbol} shows bullish setup. {rec} recommendation with {conf}% confidence."
        elif analysis.recommendation in (Recommendation.STRONG_SELL, Recommendation.SELL):
            summary = f"{analysis.symbol} shows bearish setup. {rec} recommendation with {conf}% confidence."
        else:
            summary = f"{analysis.symbol} is neutral. Recommend waiting for clearer setup."

        details = f"""Based on technical analysis:

Bullish factors:
{chr(10).join(f"• {f}" for f in analysis.bullish_factors)}

Bearish factors:
{chr(10).join(f"• {f}" for f in analysis.bearish_factors)}

Note: LLM analysis unavailable ({error}). This is rule-based analysis only."""

        return LLMResponse(
            summary=summary,
            detailed_explanation=details,
            risk_assessment="Unable to generate AI risk assessment. Consider volatility and position sizing.",
            confidence_note=f"Rule-based confidence: {conf}%",
            model_used="fallback",
            tokens_used=0,
        )

    async def is_available(self) -> bool:
        """Check if Guardian proxy is available.

        Short-circuits with GuardianUnauthenticated when GUARDIAN_API_KEY
        is absent, preventing unauthenticated polling of /v1/models.
        """
        if not self._api_key:
            logger.debug(
                "Guardian is_available: short-circuit — " "GUARDIAN_API_KEY not set (value=%r)",
                self._api_key,
            )
            raise GuardianUnauthenticated(
                "GUARDIAN_API_KEY is not set. " "Set the env var or skip Guardian LLM features."
            )
        available, _ = await self.get_models_status()
        return available

    async def list_models(self) -> list[str]:
        """List models available on the Guardian proxy.

        Short-circuits when GUARDIAN_API_KEY is absent.
        """
        if not self._api_key:
            logger.debug(
                "Guardian list_models: short-circuit — " "GUARDIAN_API_KEY not set",
            )
            return []
        _, models = await self.get_models_status()
        return models


# Backward-compat alias — callers using OllamaAnalyst still work
OllamaAnalyst = GuardianAnalyst


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


async def get_llm_analysis(
    analysis: TechnicalAnalysis,
    question: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    """Get LLM-powered analysis explanation.

    Args:
        analysis: Technical analysis to explain
        question: Optional specific question
        model: Guardian model to use (default: GLM-4.7-Flash)

    Returns:
        LLM response with explanation
    """
    analyst = GuardianAnalyst(model=model)
    return await analyst.explain(analysis, question)


async def check_guardian() -> dict:
    """Check Guardian proxy availability and list models.

    Returns:
        Dict with status and available models
    """
    analyst = GuardianAnalyst()
    try:
        available, models = await analyst.get_models_status()
    except GuardianUnauthenticated:
        # Short-circuit: no API key, no polling
        return {
            "available": False,
            "host": analyst.host,
            "default_model": analyst.model,
            "available_models": [],
            "reason": "GUARDIAN_API_KEY not set",
        }

    return {
        "available": available,
        "host": analyst.host,
        "default_model": analyst.model,
        "available_models": models,
    }


# Backward-compat alias
check_ollama = check_guardian
