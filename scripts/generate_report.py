#!/usr/bin/env python3
"""Generate regime_underperformance_report.json from analysis results.

Produces a structured report with:
- Quantified underperformance scores per regime
- Go/No-Go recommendations
- Key findings (-40% bear, -20% range)
- JSON schema validation
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.regime_underperformance_analysis import (
    Regime,
    RegimeMetrics,
    UnderperformanceFlag,
    compute_all_regime_metrics,
    compute_transition_baseline,
    compute_underperformance,
    load_oos_regime_data,
    oos_data_to_candles,
    generate_synthetic_candles,
)


# ---------------------------------------------------------------------------
# Report schema
# ---------------------------------------------------------------------------

@dataclass
class GoNoGoDecision:
    """Go/No-Go recommendation for a regime."""
    regime: str
    decision: str  # "GO", "NO-GO", "CONDITIONAL"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KeyFinding:
    """A quantified key finding."""
    metric: str
    regime: str
    value: float
    baseline: float
    delta_pct: float  # percentage change from baseline
    direction: str  # "positive", "negative", "neutral"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportMetadata:
    """Report-level metadata."""
    analysis: str
    generated_at: str
    version: str
    data_source: str
    n_candles: int
    transition_baseline: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

REPORT_SCHEMA = {
    "type": "object",
    "required": [
        "report_metadata",
        "regime_analysis",
        "key_findings",
        "go_no_go_recommendations",
        "underperformance_scores",
    ],
    "properties": {
        "report_metadata": {
            "type": "object",
            "required": ["analysis", "generated_at", "version", "data_source", "n_candles", "transition_baseline"],
            "properties": {
                "analysis": {"type": "string"},
                "generated_at": {"type": "string"},
                "version": {"type": "string"},
                "data_source": {"type": "string"},
                "n_candles": {"type": "integer"},
                "transition_baseline": {
                    "type": "object",
                    "required": ["return", "sharpe", "drawdown", "n_candles"],
                },
            },
        },
        "regime_analysis": {
            "type": "object",
            "patternProperties": {
                "^(bull|bear|range|high_vol|low_vol|transition)$": {
                    "type": "object",
                    "required": ["regime", "n_candles", "mean_return", "sharpe_ratio", "max_drawdown", "win_rate"],
                },
            },
        },
        "key_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["metric", "regime", "value", "baseline", "delta_pct", "direction"],
            },
        },
        "go_no_go_recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["regime", "decision", "confidence", "reasoning", "risk_level"],
            },
        },
        "underperformance_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["regime", "score", "is_underperforming", "return_delta", "sharpe_delta", "flags"],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_report(report: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate report against JSON schema (simplified validator)."""
    errors = []

    # Check required top-level keys
    for key in schema.get("required", []):
        if key not in report:
            errors.append(f"Missing required top-level key: {key}")

    # Validate report_metadata
    if "report_metadata" in report:
        meta = report["report_metadata"]
        for req in schema["properties"]["report_metadata"].get("required", []):
            if req not in meta:
                errors.append(f"report_metadata missing: {req}")
        tb = meta.get("transition_baseline", {})
        for req in schema["properties"]["report_metadata"]["properties"]["transition_baseline"].get("required", []):
            if req not in tb:
                errors.append(f"transition_baseline missing: {req}")

    # Validate regime_analysis
    if "regime_analysis" in report:
        for regime_name, regime_data in report["regime_analysis"].items():
            for req in schema["properties"]["regime_analysis"]["patternProperties"][
                "^(bull|bear|range|high_vol|low_vol|transition)$"
            ].get("required", []):
                if req not in regime_data:
                    errors.append(f"regime_analysis.{regime_name} missing: {req}")

    # Validate key_findings
    if "key_findings" in report:
        for i, kf in enumerate(report["key_findings"]):
            for req in schema["properties"]["key_findings"]["items"].get("required", []):
                if req not in kf:
                    errors.append(f"key_findings[{i}] missing: {req}")

    # Validate go_no_go_recommendations
    if "go_no_go_recommendations" in report:
        for i, rec in enumerate(report["go_no_go_recommendations"]):
            for req in schema["properties"]["go_no_go_recommendations"]["items"].get("required", []):
                if req not in rec:
                    errors.append(f"go_no_go_recommendations[{i}] missing: {req}")

    # Validate underperformance_scores
    if "underperformance_scores" in report:
        for i, score in enumerate(report["underperformance_scores"]):
            for req in schema["properties"]["underperformance_scores"]["items"].get("required", []):
                if req not in score:
                    errors.append(f"underperformance_scores[{i}] missing: {req}")

    return errors


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def compute_key_findings(
    regime_metrics: dict[Regime, RegimeMetrics],
    transition_baseline: dict[str, Any],
    flags: dict[str, UnderperformanceFlag],
) -> list[KeyFinding]:
    """Compute key findings from analysis results.

    Key findings include:
    - Bear regime underperformance (target: ~-40%)
    - Range regime underperformance (target: ~-20%)
    - Bull regime performance
    - Volatility regime comparison
    """
    findings = []
    trans_return = transition_baseline["return"]

    for regime_name, flag in flags.items():
        delta_pct = (flag.return_delta / trans_return * 100) if trans_return != 0 else 0.0

        direction = "negative" if delta_pct < -5 else ("positive" if delta_pct > 5 else "neutral")

        findings.append(KeyFinding(
            metric="return_delta_pct",
            regime=regime_name,
            value=flag.return_delta,
            baseline=trans_return,
            delta_pct=delta_pct,
            direction=direction,
        ))

    return findings


def compute_go_no_go(
    regime_metrics: dict[Regime, RegimeMetrics],
    flags: dict[str, UnderperformanceFlag],
) -> list[GoNoGoDecision]:
    """Compute Go/No-Go recommendations for each regime.

    Logic:
    - GO: score < 50, not underperforming or low risk
    - NO-GO: score > 100, highly underperforming
    - CONDITIONAL: score between 50-100
    """
    decisions = []

    for regime_name, flag in flags.items():
        rm = regime_metrics[Regime(regime_name)]

        # Determine decision based on score and flags
        if flag.score < 50:
            decision = "GO"
            risk_level = "LOW"
        elif flag.score > 100:
            decision = "NO-GO"
            risk_level = "HIGH"
        else:
            decision = "CONDITIONAL"
            risk_level = "MEDIUM"

        # Adjust for special cases
        if regime_name == "transition":
            decision = "GO"
            risk_level = "LOW"
            reasoning = "Baseline regime, reference point for all comparisons"
        elif "low_return" in flag.flags and "low_sharpe" in flag.flags:
            decision = "NO-GO"
            risk_level = "HIGH"
            reasoning = f"Both return and Sharpe below thresholds (score={flag.score:.1f})"
        elif "low_return" in flag.flags:
            decision = "CONDITIONAL"
            risk_level = "MEDIUM"
            reasoning = f"Return below threshold but Sharpe acceptable (score={flag.score:.1f})"
        else:
            reasoning = f"Underperformance score {flag.score:.1f} suggests {decision.lower()} (score={flag.score:.1f})"

        # Calculate confidence based on score and n_candles
        n_candles = rm.n_candles
        if n_candles == 0:
            confidence = 0.5  # Low confidence when no data
        elif flag.score < 50:
            confidence = min(0.95, 0.7 + n_candles / 10000)
        elif flag.score > 100:
            confidence = min(0.95, 0.6 + n_candles / 10000)
        else:
            confidence = 0.75

        decisions.append(GoNoGoDecision(
            regime=regime_name,
            decision=decision,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            risk_level=risk_level,
        ))

    return decisions


def generate_report(
    regime_metrics: dict[Regime, RegimeMetrics],
    transition_baseline: dict[str, Any],
    flags: dict[str, UnderperformanceFlag],
    n_candles: int,
    data_source: str = "oos_regime_dataset.json",
) -> dict[str, Any]:
    """Generate the structured JSON report."""

    # Build regime analysis section
    regime_analysis = {}
    for regime in list(Regime):
        rm = regime_metrics[regime]
        regime_analysis[regime.value] = {
            "regime": regime.value,
            "n_candles": rm.n_candles,
            "n_trades": rm.n_trades,
            "mean_return": rm.mean_return,
            "sharpe_ratio": rm.sharpe_ratio,
            "max_drawdown": rm.max_drawdown,
            "win_rate": rm.win_rate,
            "profit_factor": rm.profit_factor,
            "total_pnl": rm.total_pnl,
            "total_return": rm.total_return,
        }

    # Build key findings
    key_findings = compute_key_findings(regime_metrics, transition_baseline, flags)

    # Build go/no-go recommendations
    go_no_go = compute_go_no_go(regime_metrics, flags)

    # Build underperformance scores
    underperformance_scores = []
    for regime_name, flag in flags.items():
        underperformance_scores.append({
            "regime": regime_name,
            "score": flag.score,
            "is_underperforming": flag.is_underperforming,
            "return_delta": flag.return_delta,
            "drawdown_delta": flag.drawdown_delta,
            "sharpe_delta": flag.sharpe_delta,
            "win_rate_delta": flag.win_rate_delta,
            "flags": flag.flags,
        })

    # Build the full report
    report = {
        "report_metadata": {
            "analysis": "regime_underperformance",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "data_source": data_source,
            "n_candles": n_candles,
            "transition_baseline": {
                "return": transition_baseline["return"],
                "sharpe": transition_baseline["sharpe"],
                "drawdown": transition_baseline["drawdown"],
                "n_candles": transition_baseline["n_candles"],
            },
        },
        "regime_analysis": regime_analysis,
        "key_findings": [kf.to_dict() for kf in key_findings],
        "go_no_go_recommendations": [g.to_dict() for g in go_no_go],
        "underperformance_scores": underperformance_scores,
    }

    return report


def main():
    """Run the full report generation pipeline."""
    # Load OOS data
    oos_data = load_oos_regime_data()
    if oos_data:
        candles = oos_data_to_candles(oos_data)
        data_source = "oos_regime_dataset.json"
        print(f"Loaded {len(candles)} candles from OOS data")
    else:
        candles = generate_synthetic_candles(n=720)
        data_source = "synthetic"
        print(f"Generated {len(candles)} synthetic candles")

    # Compute transition baseline
    transition_baseline = compute_transition_baseline(candles)
    print(f"Transition baseline: return={transition_baseline['return']:+.6f}, "
          f"sharpe={transition_baseline['sharpe']:.4f}, "
          f"drawdown={transition_baseline['drawdown']:.4f}")

    # Compute per-regime metrics
    regime_metrics = compute_all_regime_metrics(candles)

    # Compute underperformance flags
    flags = compute_underperformance(regime_metrics, transition_baseline)

    # Generate report
    report = generate_report(
        regime_metrics=regime_metrics,
        transition_baseline=transition_baseline,
        flags=flags,
        n_candles=len(candles),
        data_source=data_source,
    )

    # Validate report
    errors = validate_report(report, REPORT_SCHEMA)
    if errors:
        print("\nValidation errors:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\nReport validation: PASSED")

    # Save report
    output_path = _project_root / "regime_underperformance_report.json"
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("REGIME UNDERPERFORMANCE REPORT SUMMARY")
    print("=" * 60)

    print("\nKey Findings:")
    for kf in report["key_findings"]:
        print(f"  {kf['regime']}: {kf['metric']} = {kf['value']:+.6f} "
              f"(baseline: {kf['baseline']:+.6f}, "
              f"delta: {kf['delta_pct']:+.1f}%, {kf['direction']})")

    print("\nGo/No-Go Recommendations:")
    for rec in report["go_no_go_recommendations"]:
        print(f"  {rec['regime']}: {rec['decision']} "
              f"(confidence: {rec['confidence']:.0%}, "
              f"risk: {rec['risk_level']})")
        print(f"    {rec['reasoning']}")

    print("\nUnderperformance Scores:")
    for score in report["underperformance_scores"]:
        status = "UNDERPERFORMING" if score["is_underperforming"] else "OK"
        print(f"  {score['regime']}: score={score['score']:.1f} [{status}] "
              f"(flags: {', '.join(score['flags'])})")

    print("\n" + "=" * 60)

    return report


if __name__ == "__main__":
    main()
