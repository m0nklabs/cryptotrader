"""TimesFM forecasting lane.

Zero-shot probabilistic forecasting of candle closes with Google's TimesFM 2.5
(200M, PyTorch) foundation model. Modules:

- ``models``: dataclasses for forecast points and results.
- ``service``: lazy, thread-safe model wrapper (load + batched inference).
- ``cache``: in-memory TTL cache keyed on the last closed candle timestamp.
"""

from core.forecasting.cache import ForecastCache, get_forecast_cache
from core.forecasting.models import ForecastPoint, ForecastResult
from core.forecasting.service import (
    MAX_HORIZON_DEFAULT,
    MAX_CONTEXT_DEFAULT,
    MIN_CONTEXT_POINTS,
    MODEL_ID_DEFAULT,
    QUANTILE_MEAN_IDX,
    QUANTILE_P10_IDX,
    QUANTILE_P50_IDX,
    QUANTILE_P90_IDX,
    TimesFMConfig,
    TimesFMService,
    extract_quantile_band,
    load_config_from_env,
)

__all__ = [
    "ForecastCache",
    "ForecastPoint",
    "ForecastResult",
    "MAX_CONTEXT_DEFAULT",
    "MAX_HORIZON_DEFAULT",
    "MIN_CONTEXT_POINTS",
    "MODEL_ID_DEFAULT",
    "QUANTILE_MEAN_IDX",
    "QUANTILE_P10_IDX",
    "QUANTILE_P50_IDX",
    "QUANTILE_P90_IDX",
    "TimesFMConfig",
    "TimesFMService",
    "extract_quantile_band",
    "get_forecast_cache",
    "load_config_from_env",
]
