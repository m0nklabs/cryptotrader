# Forecasting lane (TimesFM)

Probabilistic zero-shot forecasting of candle closes via Meta/Google's TimesFM
foundation models. Two interchangeable backends live behind one service
interface; the API contract (`p10`/`p50`/`p90` per forecast step) is identical
for both.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /forecast` | Forecast the next `horizon` closes for one symbol. |
| `POST /forecast/batch` | Forecast many symbols; cache misses share one batched model call. |
| `GET /forecast/status` | Load status (`loaded`, `model_id`, `device`, `ready`); first call triggers the lazy load. |

Responses carry per-step `ts`, `p10`, `p50`, `p90` (80% prediction interval
around the median), plus `model_id`, `context_len`, `device`, `cache`
(`miss`/`hit`) and end-to-end `latency_ms`. Timestamps continue the candle
clock of the last closed candle (open times).

## Backends

| Backend | Module | Default model id | Weight license |
|---|---|---|---|
| `timesfm3` (default) | `timesfm3` | `google/timesfm-3.0-pytorch` | `timesfm-non-commercial-license-v1.0` — **commercial or production use of the default pretrained weights is not permitted**. Selected deliberately by the operator on 2026-09-06 for this personal, self-hosted deployment. |
| `timesfm2_5` | `timesfm` | `google/timesfm-2.5-200m-pytorch` | Apache-2.0. |

Selection: `TIMESFM_BACKEND` = `auto` | `timesfm2_5` | `timesfm3` (default
`auto`). With `auto`, the backend is derived from `TIMESFM_MODEL_ID` (an id
containing `timesfm-3` selects 3.0); an explicit value always wins. The default
model id is `google/timesfm-3.0-pytorch`.

Backend facts (verified against the installed `timesfm` 3.0.1 source):

- 3.0 (`timesfm3.TimesFM3Evaluator`): `ModelConfig(checkpoint_path, per_core_batch_size, device, ...)`; one `predict_batch(contexts, horizon, return_quantiles=True, use_symmetric_averaging=False, make_positive=True)` call per forecast. `make_positive` clamps outputs of series whose input context is non-negative (true for closes). Quantiles: `(horizon, 9)` columns `0.1..0.9` sorted — `p10=0`, `p50=4`, `p90=8`. Context limit 15,360 points; horizon is decoded in 64-step patches and sliced back. No compile step.
- 2.5 (`timesfm.TimesFM_2p5_200M_torch`): `from_pretrained(..., torch_compile=False)` (upstream issue #328: `torch_compile=True` produces flat lines) + `model.compile(timesfm.ForecastConfig(...))`. Quantiles: `(batch, horizon, 10)` — `p10=1`, `p50=5`, `p90=9`.

Both backends surface the same p10/p50/p90 tuples; `ForecastResult.model_id`
records which model produced a result.

## Environment knobs

| Variable | Default | Meaning |
|---|---|---|
| `TIMESFM_MODEL_ID` | `google/timesfm-3.0-pytorch` | Hugging Face model id. |
| `TIMESFM_BACKEND` | `auto` | `auto` \| `timesfm2_5` \| `timesfm3`. |
| `TIMESFM_DEVICE` | `auto` | `auto` \| `cpu` \| `cuda`; `auto` pre-checks free VRAM (needs ~2 GB) and falls back to CPU on shared/oversubscribed GPUs. |
| `TIMESFM_MAX_CONTEXT` | `1024` | Data-side context limit in candles (also the 2.5 compile-time cap). |
| `TIMESFM_MAX_HORIZON` | `256` | Maximum horizon accepted by the API. |
| `TIMESFM_CACHE_TTL` | `900` s | Forecast TTL-cache lifetime. |
| `TIMESFM_PRELOAD` | `1` | `0` disables the startup preload thread. |

## Caching

Forecasts are cached in-process (TTL) keyed on
`(symbol, timeframe, horizon, last_closed_candle_open_ts)` — a new candle
invalidates the key, so the next request recomputes. Cache hits return the
identical points with `cache: "hit"` and sub-50 ms latency.

## Concurrency and lifecycle

Model load and inference run on a dedicated `ThreadPoolExecutor` (never on the
FastAPI event loop). The service is a lazy, thread-safe singleton; a failed
load is remembered for 30 s (cooldown) instead of retrying the heavy load per
request. Startup optionally preloads the model in a daemon thread
(`api.main` lifespan, fail-open).

## Verification

```bash
.venv/bin/python -m pytest tests/test_forecasting_service.py tests/test_api_forecast.py -q
ruff check core/forecasting api/routes/forecast.py tests/test_forecasting_service.py tests/test_api_forecast.py

# scratch server (production systemd units stay untouched)
DATABASE_URL=... TIMESFM_DEVICE=cpu .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8011
curl -s http://127.0.0.1:8011/forecast/status
curl -s -X POST http://127.0.0.1:8011/forecast -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSD","timeframe":"1h","horizon":24}'
```

Measured on this host (CPU, RTX 3060 + 5060 Ti fully saturated by other
workloads), 1024-candle context, horizon 24: 3.0 first inference ≈ 5.7 s,
cached ≈ 11–26 ms; 2.5 first inference ≈ 7.5 s.
