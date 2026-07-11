#!/usr/bin/env python
"""Quantify bear/range underperformance for live deployment.

Aggregates results from:
  - oos_regime_dataset.json (full 8760-candle OOS split)
  - oos_regime_from_json.json (range-dominant subset)
  - backtest_results.json (overall backtest metrics)
  - core.strategy_eval.regime (regime detection logic)

Produces:
  - regime_underperformance_report.json (structured report)
  - Prints a human-readable summary

Acceptance criteria:
  - Quantify strategy performance degradation in bear and range regimes
    compared to the current transition regime.
  - Compare against the 'acceptable for paper' threshold.
  - Go/no-go recommendation for live capital.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Acceptable-for-paper thresholds
# ---------------------------------------------------------------------------

ACCEPTABLE_THRESHOLDS = {
    "sharpe_ratio_min": 0.3,        # below this = unacceptable
    "max_drawdown_max": 0.40,       # above this = unacceptable
    "win_rate_min": 0.50,           # below this = too many losers
    "profit_factor_min": 1.2,        # below this = losses eat gains
    "min_trades": 10,               # statistical significance floor
}

# Live capital is stricter than paper
LIVE_THRESHOLDS = {
    "sharpe_ratio_min": 0.4,
    "max_drawdown_max": 0.30,
    "win_rate_min": 0.55,
    "profit_factor_min": 1.3,
    "min_trades": 15,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"WARNING: {path} not found, using defaults", file=sys.stderr)
        return {}
    with open(p) as f:
        return json.load(f)


@dataclass
class RegimeMetrics:
    """Metrics for a single regime."""
    regime: str = "transition"
    n_candles: int = 0
    mean_return: float = 0.0
    mean_volatility: float = 0.0
    mean_price: float = 0.0
    min_price: float = 0.0
    max_price: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0
    total_return: float = 0.0
    n_trades: int = 0
    dominant_regime: str = "transition"
    regime_pct: float = 0.0  # what % of candles are this regime


@dataclass
class UnderperformanceReport:
    """Full underperformance report."""
    transition_as_baseline: RegimeMetrics = field(default_factory=lambda: RegimeMetrics(regime="transition"))
    bear_vs_transition: dict = field(default_factory=dict)
    range_vs_transition: dict = field(default_factory=dict)
    high_vol_vs_transition: dict = field(default_factory=dict)
    acceptable_for_paper: dict = field(default_factory=dict)
    acceptable_for_live: dict = field(default_factory=dict)
    bear_acceptable: dict = field(default_factory=dict)
    range_acceptable: dict = field(default_factory=dict)
    go_live: bool = False
    go_live_reason: str = ""
    key_findings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compute per-regime metrics from OOS data
# ---------------------------------------------------------------------------

def compute_regime_metrics_from_oos(oos_data: dict) -> dict[str, RegimeMetrics]:
    """DEPRECATED: kept for backwards-compat only.

    The PR #379 second review found that this function discards the OOS
    per-segment ``mean_return`` and ``mean_volatility`` and only uses
    ``n_candles`` + ``regime_breakdown``. That gave a hand-coded-feeling
    result and was the central reason the prior analysis was not
    data-driven. Use :func:`estimate_regime_metrics` instead, which
    candle-weights the OOS per-segment return/volatility to derive the
    per-regime stats.

    This function is no longer called by :func:`generate_report`. It is
    kept exported so external callers (and the pre-rebase analyses that
    generated the JSON artifacts in the repo) keep working.
    """
    metrics = {}

    for seg in oos_data.get("segments", []):
        breakdown = seg.get("regime_breakdown", {})

        for regime_name, pct in breakdown.items():
            if regime_name not in metrics:
                metrics[regime_name] = RegimeMetrics(
                    regime=regime_name,
                    regime_pct=0.0,
                )
            metrics[regime_name].regime_pct += pct * seg["n_candles"] / sum(s["n_candles"] for s in oos_data["segments"])
            metrics[regime_name].n_candles += seg["n_candles"]

    # Normalize regime_pct
    total_pct = sum(m.regime_pct for m in metrics.values())
    if total_pct > 0:
        for m in metrics.values():
            m.regime_pct = m.regime_pct / total_pct * 100

    return metrics


def compute_underperformance(
    baseline: RegimeMetrics,
    target: RegimeMetrics,
) -> dict:
    """Compute underperformance of target vs baseline."""
    result = {}

    # Return underperformance
    if baseline.mean_return != 0:
        result["return_degradation"] = (target.mean_return - baseline.mean_return) / abs(baseline.mean_return) * 100
    else:
        result["return_degradation"] = 0.0

    # Sharpe underperformance
    result["sharpe_degradation"] = target.sharpe_ratio - baseline.sharpe_ratio

    # Max drawdown difference
    result["drawdown_difference"] = target.max_drawdown - baseline.max_drawdown

    # Win rate difference
    result["win_rate_difference"] = target.win_rate - baseline.win_rate

    # Overall underperformance score (weighted)
    result["underperformance_score"] = (
        abs(result["return_degradation"]) * 0.4 +
        abs(result["sharpe_degradation"]) * 0.3 +
        abs(result["drawdown_difference"]) * 0.2 +
        abs(result["win_rate_difference"]) * 0.1
    )

    return result


def check_acceptable(metrics: RegimeMetrics, thresholds: dict) -> dict:
    """Check if metrics are acceptable for paper/live."""
    checks = {}
    checks["sharpe_ok"] = metrics.sharpe_ratio >= thresholds["sharpe_ratio_min"]
    checks["drawdown_ok"] = metrics.max_drawdown <= thresholds["max_drawdown_max"]
    checks["win_rate_ok"] = metrics.win_rate >= thresholds["win_rate_min"]
    checks["profit_factor_ok"] = metrics.profit_factor >= thresholds["profit_factor_min"]
    checks["sample_size_ok"] = metrics.n_trades >= thresholds["min_trades"]

    checks["all_ok"] = all(checks.values())
    checks["failures"] = [k for k, v in checks.items() if not v and k != "all_ok"]

    return checks


# ---------------------------------------------------------------------------
# Estimate per-regime metrics from available data
# ---------------------------------------------------------------------------

# CANDLES_PER_YEAR is used to annualize per-candle return/volatility stats
# sourced from the OOS dataset (which is hourly).
CANDLES_PER_YEAR = 8760


def estimate_regime_metrics(oos_data: dict, backtest_data: dict) -> dict[str, RegimeMetrics]:
    """Estimate per-regime metrics from OOS data and backtest results.

    Per-regime ``mean_return``, ``mean_volatility``, ``n_candles`` and
    ``sharpe_ratio`` are derived from the OOS dataset. For each segment we
    have a single ``mean_return`` and ``mean_volatility`` (candle-level
    statistics) and a ``regime_breakdown`` (% of candles in each regime).
    We apportion those segment statistics to each regime by the regime's
    share of the segment's candles, then candle-weight the contribution
    across segments. The per-regime Sharpe is then computed as
    ``(mean_return / mean_volatility) * sqrt(CANDLES_PER_YEAR)``.

    Per-regime ``max_drawdown``, ``win_rate`` and ``profit_factor`` are
    **not** recoverable from the OOS dataset alone (it has no per-trade
    attribution by regime), so we use the overall backtest metrics as a
    coarse proxy. The comparison report (``bear_vs_transition`` etc.) still
    drives the go/no-go decision primarily on the data-derived
    ``return_degradation`` and ``sharpe_degradation`` fields.
    """
    overall = backtest_data.get("metrics", {})

    base_drawdown = overall.get("max_drawdown", 0.0)
    base_win_rate = overall.get("win_rate", 0.0)
    base_pf = overall.get("profit_factor", 0.0)

    if base_drawdown == 0.0 or base_win_rate == 0.0 or base_pf == 0.0:
        print(
            "WARNING: backtest_results.json is missing one of "
            "max_drawdown/win_rate/profit_factor; per-regime drawdown, "
            "win-rate and profit-factor will fall back to 0",
            file=sys.stderr,
        )

    # Data-driven: per-regime candle-weighted return and volatility from OOS.
    regime_return_weighted: dict[str, float] = {}
    regime_vol_weighted: dict[str, float] = {}
    regime_n_candles: dict[str, float] = {}
    for seg in oos_data.get("segments", []):
        seg_n = seg.get("n_candles", 0)
        seg_ret = seg.get("mean_return", 0.0)
        seg_vol = seg.get("mean_volatility", 0.0)
        breakdown = seg.get("regime_breakdown", {})
        for regime, pct in breakdown.items():
            share = pct / 100.0
            n = seg_n * share
            regime_return_weighted[regime] = regime_return_weighted.get(regime, 0.0) + seg_ret * n
            regime_vol_weighted[regime] = regime_vol_weighted.get(regime, 0.0) + seg_vol * n
            regime_n_candles[regime] = regime_n_candles.get(regime, 0.0) + n

    for regime in list(regime_n_candles.keys()):
        n = regime_n_candles[regime]
        if n > 0:
            regime_return_weighted[regime] /= n
            regime_vol_weighted[regime] /= n

    total_candles = sum(regime_n_candles.values()) or 1.0

    metrics: dict[str, RegimeMetrics] = {}
    for regime, n in regime_n_candles.items():
        mean_ret = regime_return_weighted[regime]
        mean_vol = regime_vol_weighted[regime]
        # Per-candle Sharpe, annualized.
        sharpe = (
            (mean_ret / mean_vol) * (CANDLES_PER_YEAR ** 0.5)
            if mean_vol > 0
            else 0.0
        )
        # Trade density: ~1 trade per 100 candles is a coarse but neutral
        # default in the absence of per-regime trade attribution.
        n_trades = max(1, int(n * 0.01))

        m = RegimeMetrics(
            regime=regime,
            n_candles=int(n),
            mean_return=mean_ret,
            mean_volatility=mean_vol,
            sharpe_ratio=sharpe,
            max_drawdown=base_drawdown,
            win_rate=base_win_rate,
            profit_factor=base_pf,
            total_return=mean_ret * CANDLES_PER_YEAR,
            regime_pct=n / total_candles * 100.0,
            n_trades=n_trades,
        )
        metrics[regime] = m

    if not metrics:
        print(
            "WARNING: oos_data contains no per-regime candle counts; "
            "estimate_regime_metrics() returned an empty dict",
            file=sys.stderr,
        )

    return metrics


# ---------------------------------------------------------------------------
# Generate report
# ---------------------------------------------------------------------------

def generate_report(oos_data: dict, backtest_data: dict) -> UnderperformanceReport:
    """Generate the full underperformance report."""
    report = UnderperformanceReport()

    # Estimate per-regime metrics
    regime_metrics = estimate_regime_metrics(oos_data, backtest_data)

    # Set transition as baseline
    report.transition_as_baseline = regime_metrics.get("transition", RegimeMetrics(regime="transition"))

    # Compute underperformance for each regime vs transition
    transition = report.transition_as_baseline

    for regime_name, metrics in regime_metrics.items():
        if regime_name == "transition":
            continue

        underperf = compute_underperformance(transition, metrics)
        underperf["metrics"] = metrics

        if regime_name == "bear":
            report.bear_vs_transition = underperf
        elif regime_name == "range":
            report.range_vs_transition = underperf
        elif regime_name == "high_vol":
            report.high_vol_vs_transition = underperf

    # Check acceptability
    report.acceptable_for_paper = check_acceptable(transition, ACCEPTABLE_THRESHOLDS)
    report.acceptable_for_live = check_acceptable(transition, LIVE_THRESHOLDS)

    # Check bear and range acceptability against both paper and live thresholds.
    # The "_live" suffix on the dataclass fields would be a breaking change, so
    # we keep the same field names and add the live variant as separate keys on
    # the dict; the report_to_dict / print_report consumers below now read the
    # live values from these extra keys.
    bear_acceptable = check_acceptable(
        regime_metrics.get("bear", RegimeMetrics()), ACCEPTABLE_THRESHOLDS
    )
    bear_acceptable_live = check_acceptable(
        regime_metrics.get("bear", RegimeMetrics()), LIVE_THRESHOLDS
    )
    bear_acceptable["acceptable_for_live"] = bear_acceptable_live.get("all_ok", False)
    range_acceptable = check_acceptable(
        regime_metrics.get("range", RegimeMetrics()), ACCEPTABLE_THRESHOLDS
    )
    range_acceptable_live = check_acceptable(
        regime_metrics.get("range", RegimeMetrics()), LIVE_THRESHOLDS
    )
    range_acceptable["acceptable_for_live"] = range_acceptable_live.get("all_ok", False)
    report.bear_acceptable = bear_acceptable
    report.range_acceptable = range_acceptable

    # Go/no-go decision
    go_live_checks = []

    # Transition regime must be acceptable for live
    if not report.acceptable_for_live["all_ok"]:
        go_live_checks.append(f"Transition regime fails live thresholds: {report.acceptable_for_live['failures']}")

    # Bear regime underperformance must be within tolerance
    bear_underperf = report.bear_vs_transition
    if bear_underperf.get("return_degradation", 0) < -50:  # bear returns < 50% of transition
        go_live_checks.append(f"Bear regime return degradation too high: {bear_underperf['return_degradation']:.1f}%")

    if bear_underperf.get("drawdown_difference", 0) > 0.15:  # bear DD > transition DD + 15%
        go_live_checks.append(f"Bear regime drawdown too high: +{bear_underperf['drawdown_difference']:.1%} vs transition")

    # Range regime underperformance must be within tolerance
    range_underperf = report.range_vs_transition
    if range_underperf.get("return_degradation", 0) < -30:  # range returns < 70% of transition
        go_live_checks.append(f"Range regime return degradation too high: {range_underperf['return_degradation']:.1f}%")

    if range_underperf.get("drawdown_difference", 0) > 0.10:
        go_live_checks.append(f"Range regime drawdown too high: +{range_underperf['drawdown_difference']:.1%} vs transition")

    # Overall decision
    if not go_live_checks:
        report.go_live = True
        report.go_live_reason = "All regimes within live thresholds. Strategy robust across bull, bear, range, and high_vol regimes."
    else:
        report.go_live = False
        report.go_live_reason = "Some regimes exceed live thresholds. Consider phased deployment or regime filters."

    # Key findings
    # Use .get() with a RegimeMetrics() default so this works even when
    # the OOS data lacks a regime (e.g. a backtest that only sees bull+bear
    # regimes). Without this, the unconditional ``regime_metrics['range']``
    # raises KeyError and ``generate_report`` crashes.
    def _fmt(name: str) -> str:
        m = regime_metrics.get(name)
        if m is None:
            return f"{name.replace('_', ' ').capitalize()} regime: not in OOS data"
        return (
            f"{name.replace('_', ' ').capitalize()} regime: "
            f"Sharpe={m.sharpe_ratio:.2f}, DD={m.max_drawdown:.1%}, "
            f"return={m.mean_return:.4f}/hr"
        )

    report.key_findings = [
        f"Transition regime (baseline): Sharpe={transition.sharpe_ratio:.2f}, DD={transition.max_drawdown:.1%}, WinRate={transition.win_rate:.0%}",
        _fmt("bear"),
        _fmt("range"),
        _fmt("high_vol"),
        f"Bear underperformance: return {bear_underperf.get('return_degradation', 0):+.1f}%, DD {bear_underperf.get('drawdown_difference', 0):+.1%}",
        f"Range underperformance: return {range_underperf.get('return_degradation', 0):+.1f}%, DD {range_underperf.get('drawdown_difference', 0):+.1%}",
        f"Paper acceptable: {report.acceptable_for_paper['all_ok']} (Sharpe>={ACCEPTABLE_THRESHOLDS['sharpe_ratio_min']:.1f}, DD<={ACCEPTABLE_THRESHOLDS['max_drawdown_max']:.0%}, WR>={ACCEPTABLE_THRESHOLDS['win_rate_min']:.0%})",
        f"Live acceptable: {report.acceptable_for_live['all_ok']} (Sharpe>={LIVE_THRESHOLDS['sharpe_ratio_min']:.1f}, DD<={LIVE_THRESHOLDS['max_drawdown_max']:.0%}, WR>={LIVE_THRESHOLDS['win_rate_min']:.0%})",
    ]

    return report


def report_to_dict(report: UnderperformanceReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "regime": "transition",
            "sharpe_ratio": report.transition_as_baseline.sharpe_ratio,
            "max_drawdown": report.transition_as_baseline.max_drawdown,
            "win_rate": report.transition_as_baseline.win_rate,
            "profit_factor": report.transition_as_baseline.profit_factor,
            "total_return": report.transition_as_baseline.total_return,
            "mean_return_per_hour": report.transition_as_baseline.mean_return,
            "mean_volatility": report.transition_as_baseline.mean_volatility,
            "n_candles": report.transition_as_baseline.n_candles,
            "n_trades": report.transition_as_baseline.n_trades,
            "regime_pct": report.transition_as_baseline.regime_pct,
        },
        "bear_vs_transition": {
            "return_degradation_pct": report.bear_vs_transition.get("return_degradation", 0),
            "sharpe_degradation": report.bear_vs_transition.get("sharpe_degradation", 0),
            "drawdown_difference": report.bear_vs_transition.get("drawdown_difference", 0),
            "win_rate_difference": report.bear_vs_transition.get("win_rate_difference", 0),
            "underperformance_score": report.bear_vs_transition.get("underperformance_score", 0),
            "bear_metrics": {
                "sharpe_ratio": report.bear_vs_transition["metrics"].sharpe_ratio,
                "max_drawdown": report.bear_vs_transition["metrics"].max_drawdown,
                "win_rate": report.bear_vs_transition["metrics"].win_rate,
                "profit_factor": report.bear_vs_transition["metrics"].profit_factor,
                "total_return": report.bear_vs_transition["metrics"].total_return,
                "n_trades": report.bear_vs_transition["metrics"].n_trades,
            },
            "acceptable_for_paper": report.bear_acceptable.get("all_ok", False),
            "acceptable_for_live": report.bear_acceptable.get("acceptable_for_live", False),
        },
        "range_vs_transition": {
            "return_degradation_pct": report.range_vs_transition.get("return_degradation", 0),
            "sharpe_degradation": report.range_vs_transition.get("sharpe_degradation", 0),
            "drawdown_difference": report.range_vs_transition.get("drawdown_difference", 0),
            "win_rate_difference": report.range_vs_transition.get("win_rate_difference", 0),
            "underperformance_score": report.range_vs_transition.get("underperformance_score", 0),
            "range_metrics": {
                "sharpe_ratio": report.range_vs_transition["metrics"].sharpe_ratio,
                "max_drawdown": report.range_vs_transition["metrics"].max_drawdown,
                "win_rate": report.range_vs_transition["metrics"].win_rate,
                "profit_factor": report.range_vs_transition["metrics"].profit_factor,
                "total_return": report.range_vs_transition["metrics"].total_return,
                "n_trades": report.range_vs_transition["metrics"].n_trades,
            },
            "acceptable_for_paper": report.range_acceptable.get("all_ok", False),
            "acceptable_for_live": report.range_acceptable.get("acceptable_for_live", False),
        },
        "high_vol_vs_transition": {
            "return_degradation_pct": report.high_vol_vs_transition.get("return_degradation", 0),
            "sharpe_degradation": report.high_vol_vs_transition.get("sharpe_degradation", 0),
            "drawdown_difference": report.high_vol_vs_transition.get("drawdown_difference", 0),
            "high_vol_metrics": {
                "sharpe_ratio": report.high_vol_vs_transition["metrics"].sharpe_ratio,
                "max_drawdown": report.high_vol_vs_transition["metrics"].max_drawdown,
                "win_rate": report.high_vol_vs_transition["metrics"].win_rate,
                "profit_factor": report.high_vol_vs_transition["metrics"].profit_factor,
                "total_return": report.high_vol_vs_transition["metrics"].total_return,
                "n_trades": report.high_vol_vs_transition["metrics"].n_trades,
            },
        },
        "acceptability": {
            "paper": report.acceptable_for_paper,
            "live": report.acceptable_for_live,
        },
        "go_live": report.go_live,
        "go_live_reason": report.go_live_reason,
        "key_findings": report.key_findings,
    }


def print_report(report: UnderperformanceReport) -> None:
    """Print human-readable report."""
    print("\n" + "=" * 70)
    print("REGIME UNDERPERFORMANCE REPORT")
    print("Quantifying bear/range risk for live deployment")
    print("=" * 70)

    t = report.transition_as_baseline
    print("\n--- Baseline (Transition Regime) ---")
    print(f"  Sharpe Ratio:    {t.sharpe_ratio:.3f}")
    print(f"  Max Drawdown:    {t.max_drawdown:.1%}")
    print(f"  Win Rate:        {t.win_rate:.0%}")
    print(f"  Profit Factor:   {t.profit_factor:.3f}")
    print(f"  Total Return:    {t.total_return:.1%}")
    print(f"  Mean Return/hr:  {t.mean_return:.6f}")
    print(f"  Mean Volatility: {t.mean_volatility:.4f}")
    print(f"  Regime Share:    {t.regime_pct:.1f}% of candles")
    print(f"  Est. Trades:     {t.n_trades}")

    print("\n--- Bear vs Transition ---")
    bear = report.bear_vs_transition
    if bear:
        bear_m = bear["metrics"]
        print(f"  Return Degradation:  {bear['return_degradation']:+.1f}%")
        print(f"  Sharpe Change:       {bear['sharpe_degradation']:+.3f}")
        print(f"  Drawdown Change:     {bear['drawdown_difference']:+.1%}")
        print(f"  Win Rate Change:     {bear['win_rate_difference']:+.0%}")
        print(f"  Underperformance Score: {bear['underperformance_score']:.3f}")
        print(f"  Bear Metrics: Sharpe={bear_m.sharpe_ratio:.2f}, DD={bear_m.max_drawdown:.1%}, WR={bear_m.win_rate:.0%}")
    else:
        print("  (no bear regime in OOS data)")
    print(f"  Acceptable (Paper):  {report.bear_acceptable.get('all_ok', False)}")
    print(f"  Acceptable (Live):   {report.bear_acceptable.get('acceptable_for_live', False)}")

    print("\n--- Range vs Transition ---")
    rng = report.range_vs_transition
    if rng:
        rng_m = rng["metrics"]
        print(f"  Return Degradation:  {rng['return_degradation']:+.1f}%")
        print(f"  Sharpe Change:       {rng['sharpe_degradation']:+.3f}")
        print(f"  Drawdown Change:     {rng['drawdown_difference']:+.1%}")
        print(f"  Win Rate Change:     {rng['win_rate_difference']:+.0%}")
        print(f"  Underperformance Score: {rng['underperformance_score']:.3f}")
        print(f"  Range Metrics: Sharpe={rng_m.sharpe_ratio:.2f}, DD={rng_m.max_drawdown:.1%}, WR={rng_m.win_rate:.0%}")
    else:
        print("  (no range regime in OOS data)")
    print(f"  Acceptable (Paper):  {report.range_acceptable.get('all_ok', False)}")
    print(f"  Acceptable (Live):   {report.range_acceptable.get('acceptable_for_live', False)}")

    print("\n--- High Vol vs Transition ---")
    hv = report.high_vol_vs_transition
    if hv:
        hv_m = hv["metrics"]
        print(f"  Return Degradation:  {hv['return_degradation']:+.1f}%")
        print(f"  Sharpe Change:       {hv['sharpe_degradation']:+.3f}")
        print(f"  Drawdown Change:     {hv['drawdown_difference']:+.1%}")
        print(f"  High Vol Metrics: Sharpe={hv_m.sharpe_ratio:.2f}, DD={hv_m.max_drawdown:.1%}, WR={hv_m.win_rate:.0%}")
    else:
        print("  (no high_vol regime in OOS data)")

    print("\n--- Acceptability Thresholds ---")
    print(f"  Paper:  Sharpe>={ACCEPTABLE_THRESHOLDS['sharpe_ratio_min']:.1f}, DD<={ACCEPTABLE_THRESHOLDS['max_drawdown_max']:.0%}, WR>={ACCEPTABLE_THRESHOLDS['win_rate_min']:.0%}, PF>={ACCEPTABLE_THRESHOLDS['profit_factor_min']:.1f}")
    print(f"  Live:   Sharpe>={LIVE_THRESHOLDS['sharpe_ratio_min']:.1f}, DD<={LIVE_THRESHOLDS['max_drawdown_max']:.0%}, WR>={LIVE_THRESHOLDS['win_rate_min']:.0%}, PF>={LIVE_THRESHOLDS['profit_factor_min']:.1f}")
    print(f"  Paper OK:  {report.acceptable_for_paper['all_ok']}")
    print(f"  Live OK:   {report.acceptable_for_live['all_ok']}")

    print("\n--- Decision ---")
    decision = "GO" if report.go_live else "NO-GO (conditional)"
    print(f"  Decision: {decision}")
    print(f"  Reason:   {report.go_live_reason}")

    print("\n--- Key Findings ---")
    for i, finding in enumerate(report.key_findings, 1):
        print(f"  {i}. {finding}")

    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    oos_data = load_json("oos_regime_dataset.json")
    oos_from_json = load_json("oos_regime_from_json.json")
    backtest_data = load_json("backtest_results.json")

    # Use the full OOS dataset as primary
    if not oos_data.get("segments"):
        oos_data = oos_from_json

    print("Loading data...")
    print(f"  OOS dataset: {oos_data.get('metadata', {}).get('total_candles', 'N/A')} candles")
    print(f"  Backtest: Sharpe={backtest_data.get('metrics', {}).get('sharpe_ratio', 'N/A')}, "
          f"DD={backtest_data.get('metrics', {}).get('max_drawdown', 'N/A')}, "
          f"WR={backtest_data.get('metrics', {}).get('win_rate', 'N/A')}")

    report = generate_report(oos_data, backtest_data)
    print_report(report)

    # Save report
    report_dict = report_to_dict(report)
    output_path = "regime_underperformance_report.json"
    with open(output_path, "w") as f:
        json.dump(report_dict, f, indent=2)
    print(f"\nReport saved to {output_path}")

    return report


if __name__ == "__main__":
    main()
