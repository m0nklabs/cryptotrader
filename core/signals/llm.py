"""Ollama LLM integration for natural language trading analysis.

Provides AI-powered explanations and insights for trading decisions.
Uses local Ollama models for privacy and cost efficiency.

Usage:
    from core.signals.llm import OllamaAnalyst, get_llm_analysis

    # Quick analysis
    explanation = await get_llm_analysis(analysis, question="should I buy?")

    # Full analyst
    analyst = OllamaAnalyst(model="llama3.2")
    response = await analyst.explain(analysis)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from core.signals.reasoning import TechnicalAnalysis, Recommendation

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM analysis."""

    summary: str
    detailed_explanation: str
    risk_assessment: str
    confidence_note: str
    model_used: str
    tokens_used: int = 0


class OllamaAnalyst:
    """Ollama-based trading analyst for natural language explanations."""

    DEFAULT_MODEL = "llama3.2"
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
        """Initialize Ollama analyst.

        Args:
            model: Ollama model name (default: llama3.2)
            host: Ollama API host (default: http://localhost:11434)
            timeout: Request timeout in seconds
        """
        self.model = model or os.environ.get("OLLAMA_MODEL", self.DEFAULT_MODEL)
        self.host = host or os.environ.get("OLLAMA_HOST", self.DEFAULT_HOST)
        self.timeout = timeout
        # HTTP Basic Auth for ollama_guardian proxy (optional)
        self._auth_user = os.environ.get("OLLAMA_USER")
        self._auth_password = os.environ.get("OLLAMA_PASSWORD", "")
        self._auth: httpx.BasicAuth | None = (
            httpx.BasicAuth(username=self._auth_user, password=self._auth_password) if self._auth_user else None
        )

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
            response = await self._query_ollama(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.exception(f"Ollama query failed: {e}")
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
            response = await self._query_ollama(prompt, max_tokens=100)
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
            response = await self._query_ollama(prompt, max_tokens=500)
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

    async def _query_ollama(
        self,
        prompt: str,
        max_tokens: int = 1000,
    ) -> dict:
        """Query Ollama API."""
        url = f"{self.host}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": self.SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            },
        }

        async with httpx.AsyncClient(auth=self._auth) as client:
            response = await client.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()

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
        """Check if Ollama is available."""
        try:
            async with httpx.AsyncClient(auth=self._auth) as client:
                response = await client.get(f"{self.host}/api/tags", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available Ollama models."""
        try:
            async with httpx.AsyncClient(auth=self._auth) as client:
                response = await client.get(f"{self.host}/api/tags", timeout=5.0)
                response.raise_for_status()
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")
            return []


# Convenience functions
async def get_llm_analysis(
    analysis: TechnicalAnalysis,
    question: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    """Get LLM-powered analysis explanation.

    Args:
        analysis: Technical analysis to explain
        question: Optional specific question
        model: Ollama model to use

    Returns:
        LLM response with explanation
    """
    analyst = OllamaAnalyst(model=model)
    return await analyst.explain(analysis, question)


async def check_ollama() -> dict:
    """Check Ollama availability and list models.

    Returns:
        Dict with status and available models
    """
    analyst = OllamaAnalyst()
    available = await analyst.is_available()
    models = await analyst.list_models() if available else []

    return {
        "available": available,
        "host": analyst.host,
        "default_model": analyst.model,
        "available_models": models,
    }
