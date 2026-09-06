#!/usr/bin/env python3
"""Walk-forward forecast-quality evaluation for the TimesFM lane.

Empirically answers "are the /forecast predictions any good?" for both TimesFM
backends against simple baselines, using the operator's own candle data.

Method (rolling-origin walk-forward):
  - Load the full close series for one symbol/timeframe from the ``candles``
    table (same access pattern as ``api/routes/forecast.py::_fetch_closes``:
    filter on exchange/symbol/timeframe, order by ``open_time``).
  - Build ``--origins`` evaluation windows ending at the most recent origin
    that still has ``--horizon`` known future closes, spaced ``--origin-step``
    candles apart. Each origin feeds the model exactly ``--context`` closes
    (the same input shape the ``/forecast`` route uses) and is scored against
    the next ``--horizon`` actual closes.
  - Each backend runs as ONE batched ``TimesFMService.forecast()`` call over
    all origin windows (the service is batched; no per-origin loop).
  - Baselines computed in numpy on the same origins:
      * persistence       — last observed close repeated for every step.
      * seasonal-naive    — close at the same wall-clock slot one seasonal
        period earlier (default 7 days: e.g. 168 steps back on 1h data),
        aligned per step; falls back to persistence for steps whose seasonal
        slot is missing from the data (gaps / start of history).

Metrics per method: MAE, MAPE %, RMSE, directional accuracy (chain sign match,
pooled over all origin steps) and last-step directional accuracy (net move over
the whole horizon). Model backends additionally report p10-p90 coverage
(target ~80%) and mean band width as % of price.

Results are printed as a comparison table and written to
``research/forecast_eval/eval_<symbol>_<timeframe>_h<horizon>_<ts>.json``
(the ``research/`` directory is gitignored).

Usage:
    .venv/bin/python scripts/evaluate_forecast.py \
        --symbol BTCUSD --timeframe 1h --horizon 24 --origins 60 --origin-step 24

    # secondary run (1m, one hour ahead):
    .venv/bin/python scripts/evaluate_forecast.py \
        --symbol BTCUSD --timeframe 1m --horizon 60 --origins 30 --origin-step 60
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Make the repo root importable when the script is run from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.forecasting.service import (  # noqa: E402
    MODEL_ID_DEFAULT_2_5,
    MODEL_ID_DEFAULT_3_0,
    TimesFMConfig,
    TimesFMService,
)

logger = logging.getLogger("evaluate_forecast")

TIMEFRAME_RE = re.compile(r"^(\d+)([mhdw])$")
TIMEFRAME_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}

# Default seasonal period: one week ("same hour last week" on 1h data).
SEASONAL_PERIOD_DAYS = 7.0

DEFAULT_OUTPUT_DIR = REPO_ROOT / "research" / "forecast_eval"

BACKEND_3_0 = "timesfm3"
BACKEND_2_5 = "timesfm2_5"
BACKEND_CHOICES = (BACKEND_3_0, BACKEND_2_5, "both")

# Metric keys in display order.
METRIC_LABELS = (
    ("mae", "MAE"),
    ("mape_pct", "MAPE %"),
    ("rmse", "RMSE"),
    ("dir_acc_overall", "DirAcc overall"),
    ("dir_acc_last_step", "DirAcc last-step"),
    ("coverage_p10_p90", "p10-p90 coverage"),
    ("mean_band_width_pct", "Band width %"),
)


# ======================================================================
# Data loading
# ======================================================================


def load_database_url() -> str:
    """Return DATABASE_URL from the environment or the repo ``.env`` file.

    Never logs or returns the URL itself to stdout; only used for the engine.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip().strip("'\"")
    raise SystemExit("DATABASE_URL not found in environment or .env")


def fetch_candles(
    database_url: str, exchange: str, symbol: str, timeframe: str
) -> tuple[list[int], np.ndarray]:
    """Fetch all candles for the series, ascending by open time.

    Reuses the same table/columns as the ``/forecast`` route (``candles``
    filtered on exchange/symbol/timeframe). Timestamps are epoch milliseconds
    of the candle open times (the DB stores naive UTC timestamps).

    Returns:
        Tuple ``(open_times_ms, closes)``.
    """
    import sqlalchemy as sa

    engine = sa.create_engine(database_url)
    stmt = sa.text(
        """
        SELECT open_time, close
        FROM candles
        WHERE exchange = :exchange
          AND symbol = :symbol
          AND timeframe = :timeframe
        ORDER BY open_time ASC
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                stmt, {"exchange": exchange, "symbol": symbol, "timeframe": timeframe}
            ).fetchall()
    finally:
        engine.dispose()

    if not rows:
        raise SystemExit(f"No candles found for {exchange}:{symbol}:{timeframe}")

    open_times_ms: list[int] = []
    closes: list[float] = []
    for open_time, close in rows:
        dt = open_time if open_time.tzinfo else open_time.replace(tzinfo=timezone.utc)
        open_times_ms.append(int(dt.timestamp() * 1000))
        closes.append(float(close))
    return open_times_ms, np.asarray(closes, dtype=np.float64)


def find_gaps(open_times_ms: list[int], timeframe_ms: int) -> list[dict[str, object]]:
    """Return gaps (missing candles) as (start, end, missing) descriptors."""
    gaps: list[dict[str, object]] = []
    for prev, cur in zip(open_times_ms, open_times_ms[1:], strict=False):
        delta = cur - prev
        if delta > timeframe_ms:
            missing = int(round(delta / timeframe_ms)) - 1
            gaps.append(
                {
                    "after_open_time": _iso_ms(prev),
                    "next_open_time": _iso_ms(cur),
                    "missing_candles": missing,
                }
            )
    return gaps


# ======================================================================
# Origin construction
# ======================================================================


class Origin:
    """One evaluation origin: context window, targets and actuals."""

    __slots__ = ("end_idx", "context", "actuals", "target_ts_ms", "last_close")

    def __init__(
        self,
        end_idx: int,
        context: np.ndarray,
        actuals: np.ndarray,
        target_ts_ms: list[int],
        last_close: float,
    ) -> None:
        self.end_idx = end_idx
        self.context = context
        self.actuals = actuals
        self.target_ts_ms = target_ts_ms
        self.last_close = last_close


def build_origins(
    open_times_ms: list[int],
    closes: np.ndarray,
    context: int,
    origins: int,
    origin_step: int,
    horizon: int,
) -> list[Origin]:
    """Build rolling-origin windows ending at the latest fully-evaluable point.

    The most recent origin is the one whose ``horizon`` following closes are
    all present in the data; earlier origins are spaced ``origin_step``
    candles apart. Each context window is the ``context`` closes ending at
    (and including) the origin candle — the same shape the ``/forecast``
    route feeds the model.
    """
    n = len(closes)
    last_eval_end = n - horizon - 1  # index of last context candle, latest origin
    earliest_end = last_eval_end - (origins - 1) * origin_step
    if earliest_end - context + 1 < 0:
        raise SystemExit(
            f"Not enough data: need context({context}) + (origins-1)*step({origins - 1}*{origin_step}) "
            f"+ horizon({horizon}) = {context + (origins - 1) * origin_step + horizon} closes, "
            f"got {n}"
        )

    out: list[Origin] = []
    for k in range(origins):
        end_idx = last_eval_end - (origins - 1 - k) * origin_step
        context_arr = closes[end_idx - context + 1 : end_idx + 1]
        actuals = closes[end_idx + 1 : end_idx + 1 + horizon]
        target_ts = open_times_ms[end_idx + 1 : end_idx + 1 + horizon]
        if len(context_arr) != context or len(actuals) != horizon:
            raise SystemExit(f"Origin {k}: incomplete window (data gap at the window edge?)")
        out.append(
            Origin(
                end_idx=end_idx,
                context=context_arr,
                actuals=actuals,
                target_ts_ms=target_ts,
                last_close=float(closes[end_idx]),
            )
        )
    return out


# ======================================================================
# Baselines
# ======================================================================


def baseline_persistence(origins: list[Origin], horizon: int) -> np.ndarray:
    """Last observed close repeated for every forecast step. Shape (origins, horizon)."""
    return np.tile(
        np.asarray([o.last_close for o in origins], dtype=np.float64)[:, None], (1, horizon)
    )


def baseline_seasonal_naive(
    origins: list[Origin],
    ts_to_close: dict[int, float],
    seasonal_delta_ms: int,
) -> tuple[np.ndarray, int]:
    """Same wall-clock slot one seasonal period earlier, aligned per step.

    For forecast step ``t`` of an origin, look up the close at
    ``target_ts[t] - seasonal_delta`` (e.g. exactly one week earlier). Falls
    back to the persistence value when that slot is missing (data gap or
    start of history).

    Returns:
        Tuple (predictions shaped (origins, horizon), fallback_step_count).
    """
    preds = np.empty((len(origins), len(origins[0].target_ts_ms)), dtype=np.float64)
    fallbacks = 0
    for i, origin in enumerate(origins):
        for t, target_ts in enumerate(origin.target_ts_ms):
            seasonal = ts_to_close.get(target_ts - seasonal_delta_ms)
            if seasonal is None:
                preds[i, t] = origin.last_close
                fallbacks += 1
            else:
                preds[i, t] = seasonal
    return preds, fallbacks


# ======================================================================
# Metrics
# ======================================================================


def directional_accuracy(pred: np.ndarray, origins: list[Origin]) -> tuple[float, float]:
    """Return (overall, last-step) directional accuracy.

    Overall: per step, sign of the chain change (step 0 is measured against
    the last observed close) must match the sign of the actual chain change.
    Last-step: sign of the net move over the whole horizon (last forecast step
    vs last observed close) must match the actual net move.
    """
    total = 0
    matches = 0
    for i, origin in enumerate(origins):
        actuals = origin.actuals
        forecast = pred[i]
        prev_actual = origin.last_close
        prev_forecast = origin.last_close
        for t in range(len(actuals)):
            total += 1
            f_change = forecast[t] - prev_forecast
            a_change = actuals[t] - prev_actual
            matches += int(np.sign(f_change) == np.sign(a_change))
            prev_actual = actuals[t]
            prev_forecast = forecast[t]

    total_last = len(origins)
    matches_last = 0
    for i, origin in enumerate(origins):
        last_idx = len(origin.actuals) - 1
        f_net = pred[i][last_idx] - origin.last_close
        a_net = origin.actuals[last_idx] - origin.last_close
        matches_last += int(np.sign(f_net) == np.sign(a_net))

    overall = matches / total if total else 0.0
    last = matches_last / total_last if total_last else 0.0
    return overall, last


def compute_metrics(
    pred: np.ndarray,
    origins: list[Origin],
    band: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> dict[str, float | int]:
    """Compute MAE / MAPE % / RMSE / directional accuracy (+ band metrics)."""
    actuals = np.stack([o.actuals for o in origins])  # (origins, horizon)
    err = pred - actuals
    nonzero = actuals != 0
    mape = float(np.mean(np.abs(err[nonzero] / actuals[nonzero])) * 100.0)
    dir_overall, dir_last = directional_accuracy(pred, origins)

    metrics: dict[str, float | int] = {
        "mae": float(np.mean(np.abs(err))),
        "mape_pct": mape,
        "rmse": float(np.sqrt(np.mean(err**2))),
        "dir_acc_overall": dir_overall,
        "dir_acc_last_step": dir_last,
    }

    if band is not None:
        p10, _p50, p90 = band
        inside = (actuals >= p10) & (actuals <= p90)
        width_pct = (p90 - p10) / np.where(actuals == 0, np.nan, actuals) * 100.0
        metrics["coverage_p10_p90"] = float(np.mean(inside))
        metrics["mean_band_width_pct"] = float(np.nanmean(width_pct))
    return metrics


# ======================================================================
# Model backends
# ======================================================================


def run_backend(
    backend: str,
    series: list[np.ndarray],
    horizon: int,
    context: int,
    device: str,
) -> tuple[list[list[tuple[float, float, float]]], dict[str, object]]:
    """Run one backend: load the model once, forecast all series in one call.

    Backend selection is explicit via ``TimesFMConfig`` (equivalent to the
    route's env-based selection: ``TIMESFM_BACKEND`` / ``TIMESFM_MODEL_ID``).

    Returns:
        Tuple (bands, runtime_info) where bands[i] is the (p10, p50, p90)
        tuple list per horizon step for series i.
    """
    model_id = MODEL_ID_DEFAULT_3_0 if backend == BACKEND_3_0 else MODEL_ID_DEFAULT_2_5
    config = TimesFMConfig(
        model_id=model_id,
        backend=backend,
        device=device,
        max_context=max(1024, context),
        max_horizon=max(256, horizon),
    )
    service = TimesFMService(config)

    load_started = time.perf_counter()
    service.load()
    load_s = time.perf_counter() - load_started

    forecast_started = time.perf_counter()
    bands = service.forecast(series, horizon)
    forecast_s = time.perf_counter() - forecast_started

    info: dict[str, object] = {
        "backend": backend,
        "model_id": model_id,
        "device": service.device,
        "load_s": round(load_s, 2),
        "forecast_s": round(forecast_s, 2),
        "batch_size": len(series),
    }

    # Free the model before the next backend loads.
    del service
    gc.collect()
    return bands, info


def bands_to_arrays(
    bands: list[list[tuple[float, float, float]]], horizon: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split service output into p50 predictions and (p10, p90) band arrays."""
    p50 = np.asarray([[step[1] for step in b] for b in bands], dtype=np.float64)
    p10 = np.asarray([[step[0] for step in b] for b in bands], dtype=np.float64)
    p90 = np.asarray([[step[2] for step in b] for b in bands], dtype=np.float64)
    return p50, p10, p90, p50


# ======================================================================
# Reporting
# ======================================================================


def _iso_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def print_table(columns: list[tuple[str, dict[str, float | int]]]) -> None:
    """Print the metric comparison table (metrics as rows, methods as columns)."""
    header = f"{'metric':<20}" + "".join(f"{name:>22}" for name, _ in columns)
    print("\n" + "=" * len(header))
    print("Walk-forward forecast quality  (pooled over all origins x horizon steps)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for key, label in METRIC_LABELS:
        row = f"{label:<20}"
        for _name, metrics in columns:
            value = metrics.get(key)
            cell = "—" if value is None else f"{value:.4f}"
            row += f"{cell:>22}"
        print(row)
    print("-" * len(header))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Walk-forward forecast-quality evaluation for the TimesFM lane."
    )
    parser.add_argument("--exchange", default="bitfinex", help="Exchange code (default: bitfinex)")
    parser.add_argument("--symbol", default="BTCUSD", help="Symbol without slash (default: BTCUSD)")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe, e.g. 1h, 1m")
    parser.add_argument("--horizon", type=int, default=24, help="Forecast horizon in candles")
    parser.add_argument("--origins", type=int, default=60, help="Number of evaluation origins")
    parser.add_argument("--origin-step", type=int, default=24, help="Candles between origins")
    parser.add_argument("--context", type=int, default=1024, help="Context closes per origin")
    parser.add_argument(
        "--backend",
        choices=BACKEND_CHOICES,
        default="both",
        help="Backends to evaluate (default: both)",
    )
    parser.add_argument(
        "--seasonal-period",
        type=float,
        default=0.0,
        help="Seasonal period in candles (0 = auto: 7 days worth, e.g. 168 on 1h)",
    )
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"))
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for the results JSON (default: research/forecast_eval)",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = parse_args()

    match = TIMEFRAME_RE.match(args.timeframe.strip().lower())
    if not match:
        raise SystemExit(f"Cannot parse timeframe {args.timeframe!r}")
    timeframe_ms = int(match.group(1)) * TIMEFRAME_UNIT_MS[match.group(2)]

    horizon, origins, origin_step, context = args.horizon, args.origins, args.origin_step, args.context
    if min(horizon, origins, origin_step, context) < 1:
        raise SystemExit("horizon, origins, origin-step and context must be positive")

    print(f"Loading candles for {args.exchange}:{args.symbol}:{args.timeframe} ...")
    database_url = load_database_url()
    open_times_ms, closes = fetch_candles(database_url, args.exchange, args.symbol, args.timeframe)
    n = len(closes)
    print(f"  {n} closes  ({_iso_ms(open_times_ms[0])} .. {_iso_ms(open_times_ms[-1])})")

    if np.isnan(closes).any():
        raise SystemExit("NaN values found in close series — aborting (data quality issue)")

    # Seasonal period: default one week expressed in candles.
    if args.seasonal_period > 0:
        seasonal_period = float(args.seasonal_period)
    else:
        seasonal_period = SEASONAL_PERIOD_DAYS * 86_400_000 / timeframe_ms
    seasonal_delta_ms = int(round(seasonal_period * timeframe_ms))

    origins_list = build_origins(open_times_ms, closes, context, origins, origin_step, horizon)
    first_origin_ts = open_times_ms[origins_list[0].end_idx]
    last_origin_ts = open_times_ms[origins_list[-1].end_idx]
    print(
        f"  {origins} origins, step {origin_step}, context {context}, horizon {horizon}\n"
        f"  eval window: origin {_iso_ms(first_origin_ts)} .. {_iso_ms(last_origin_ts)} "
        f"(actuals end {_iso_ms(origins_list[-1].target_ts_ms[-1])})\n"
        f"  seasonal period: {seasonal_period:g} candles ({seasonal_delta_ms / 86_400_000:.1f} days)"
    )

    # Data-quality scan over the full span the evaluation touches.
    span_start_idx = origins_list[0].end_idx - context + 1
    gaps_in_span = find_gaps(open_times_ms[span_start_idx:], timeframe_ms)

    ts_to_close = dict(zip(open_times_ms, (float(c) for c in closes), strict=True))

    persistence = baseline_persistence(origins_list, horizon)
    seasonal, seasonal_fallbacks = baseline_seasonal_naive(origins_list, ts_to_close, seasonal_delta_ms)
    print(
        f"  seasonal-naive fallback steps (missing seasonal slot): {seasonal_fallbacks}"
        f" / {origins * horizon}"
    )

    backends = [BACKEND_3_0, BACKEND_2_5] if args.backend == "both" else [args.backend]

    series = [o.context for o in origins_list]
    columns: list[tuple[str, dict[str, float | int]]] = []
    runtime_info: dict[str, object] = {}
    results: dict[str, dict[str, float | int]] = {}
    per_origin_mae: dict[str, list[float]] = {}

    persistence_metrics = compute_metrics(persistence, origins_list)
    seasonal_metrics = compute_metrics(seasonal, origins_list)
    per_origin_mae["persistence"] = np.mean(
        np.abs(persistence - np.stack([o.actuals for o in origins_list])), axis=1
    ).tolist()
    per_origin_mae["seasonal_naive"] = np.mean(
        np.abs(seasonal - np.stack([o.actuals for o in origins_list])), axis=1
    ).tolist()

    for backend in backends:
        label = "TimesFM 3.0" if backend == BACKEND_3_0 else "TimesFM 2.5"
        print(f"\nRunning backend {backend} ({len(series)} series x horizon {horizon}, device={args.device}) ...")
        bands, info = run_backend(backend, series, horizon, context, args.device)
        runtime_info[backend] = info
        print(f"  load {info['load_s']}s, forecast {info['forecast_s']}s on {info['device']}")

        p50, p10, p90, _ = bands_to_arrays(bands, horizon)
        metrics = compute_metrics(p50, origins_list, band=(p10, p50, p90))
        results[backend] = metrics
        per_origin_mae[backend] = np.mean(
            np.abs(p50 - np.stack([o.actuals for o in origins_list])), axis=1
        ).tolist()
        columns.append((f"{label} p50", metrics))

    columns.append(("Persistence", persistence_metrics))
    columns.append((f"SeasonalNaive({seasonal_period:g})", seasonal_metrics))

    print_table(columns)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"eval_{args.symbol}_{args.timeframe}_h{horizon}_{timestamp}.json"

    payload = {
        "symbol": args.symbol,
        "exchange": args.exchange,
        "timeframe": args.timeframe,
        "horizon": horizon,
        "origins": origins,
        "origin_step": origin_step,
        "context": context,
        "device": args.device,
        "seasonal_period_candles": seasonal_period,
        "data": {
            "rows": n,
            "first_open_time": _iso_ms(open_times_ms[0]),
            "last_open_time": _iso_ms(open_times_ms[-1]),
            "eval_window": {
                "first_origin_open_time": _iso_ms(first_origin_ts),
                "last_origin_open_time": _iso_ms(last_origin_ts),
                "last_actual_open_time": _iso_ms(origins_list[-1].target_ts_ms[-1]),
            },
            "gaps_in_eval_span": gaps_in_span,
            "seasonal_naive_fallback_steps": seasonal_fallbacks,
            "total_scored_steps": origins * horizon,
        },
        "runtime": runtime_info,
        "results": results,
        "per_origin_mae": per_origin_mae,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nResults written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
