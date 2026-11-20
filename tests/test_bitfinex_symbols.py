from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data.bitfinex_symbols import normalize_bitfinex_symbol


# Internal symbols as stored in the database and in the per-instance env files.
# Bitfinex serves AVAX/DOGE/LINK only in colon-separated form; everything else
# in this set is concatenated. Regression cover for issue #469.
CONCAT_FORM_SYMBOLS = [
    "ADAUSD",
    "APTUSD",
    "ARBUSD",
    "BTCUSD",
    "CHZUSD",
    "CRVUSD",
    "DOTUSD",
    "EOSUSD",
    "ETCUSD",
    "ETHUSD",
    "FETUSD",
    "FILUSD",
    "LDOUSD",
    "LTCUSD",
    "NEOUSD",
    "SEIUSD",
    "SOLUSD",
    "SUIUSD",
    "UNIUSD",
    "XRPUSD",
]

COLON_FORM_SYMBOLS = ["AVAXUSD", "DOGEUSD", "LINKUSD"]


@pytest.mark.parametrize("symbol", CONCAT_FORM_SYMBOLS)
def test_concatenated_markets_keep_the_concatenated_shape(symbol: str) -> None:
    """Markets Bitfinex serves as ``tBTCUSD`` must not gain a colon."""
    assert normalize_bitfinex_symbol(symbol) == f"t{symbol}"


@pytest.mark.parametrize("symbol", COLON_FORM_SYMBOLS)
def test_colon_form_markets_are_split(symbol: str) -> None:
    """``tAVAXUSD`` answers with ``[]``; the API needs ``tAVAX:USD``."""
    expected = f"t{symbol[:-3]}:USD"
    assert normalize_bitfinex_symbol(symbol) == expected


@pytest.mark.parametrize("symbol", COLON_FORM_SYMBOLS)
def test_result_is_the_form_the_candles_endpoint_accepts(symbol: str) -> None:
    """The colon form carries the quote onto the base, not a stray concat suffix."""
    normalized = normalize_bitfinex_symbol(symbol)
    base, _, quote = normalized[1:].partition(":")
    assert base == symbol[:-3]
    assert quote == "USD"


def test_already_colon_separated_symbol_keeps_its_shape() -> None:
    assert normalize_bitfinex_symbol("AVAX:USD") == "tAVAX:USD"
    assert normalize_bitfinex_symbol("BTC:USD") == "tBTC:USD"


def test_already_prefixed_api_symbol_is_returned_verbatim() -> None:
    assert normalize_bitfinex_symbol("tBTCUSD") == "tBTCUSD"
    assert normalize_bitfinex_symbol("tAVAX:USD") == "tAVAX:USD"


def test_base_starting_with_t_is_not_corrupted() -> None:
    """A 't' prefix must never be stripped from an internal symbol (tTRXUSD)."""
    assert normalize_bitfinex_symbol("TRXUSD") == "tTRXUSD"
    assert normalize_bitfinex_symbol("tTRXUSD") == "tTRXUSD"


def test_surrounding_whitespace_is_trimmed() -> None:
    assert normalize_bitfinex_symbol(" BTCUSD ") == "tBTCUSD"
    assert normalize_bitfinex_symbol("\tAVAXUSD\n") == "tAVAX:USD"


def test_unknown_base_falls_back_to_the_concatenated_shape() -> None:
    """Bases absent from the published split are passed through unchanged."""
    assert normalize_bitfinex_symbol("ZZZUSD") == "tZZZUSD"


@pytest.mark.parametrize("symbol", ["", "   ", "\n\t"])
def test_empty_symbol_raises(symbol: str) -> None:
    with pytest.raises(ValueError):
        normalize_bitfinex_symbol(symbol)


def test_normalization_is_idempotent() -> None:
    for symbol in CONCAT_FORM_SYMBOLS + COLON_FORM_SYMBOLS:
        once = normalize_bitfinex_symbol(symbol)
        assert normalize_bitfinex_symbol(once) == once


@pytest.mark.parametrize("symbol", COLON_FORM_SYMBOLS)
def test_backfill_feed_requests_the_translated_symbol(symbol: str) -> None:
    """The request helper must receive the translation, not the raw internal symbol.

    Asserting on the network boundary is what catches a feed that silently stops
    using the shared normalizer (or grows a local ``t``-prefix again), which a
    call to the imported helper alone would not.
    """
    from datetime import datetime, timezone

    from core.market_data import bitfinex_backfill as backfill

    with patch.object(backfill, "_fetch_bitfinex_candles_page", return_value=[]) as fetch:
        list(
            backfill._iter_bitfinex_candles(
                exchange="bitfinex",
                symbol=symbol,
                timeframe="1d",
                start=datetime(2025, 2, 2, tzinfo=timezone.utc),
                end=datetime(2025, 2, 10, tzinfo=timezone.utc),
            )
        )

    assert fetch.call_args.kwargs["symbol"] == f"t{symbol[:-3]}:USD"


@pytest.mark.parametrize("symbol", COLON_FORM_SYMBOLS)
def test_gap_repair_feed_requests_the_translated_symbol(symbol: str) -> None:
    from datetime import datetime, timezone

    from core.market_data import bitfinex_gap_repair as gap_repair

    with patch.object(gap_repair, "_fetch_bitfinex_candles_page", return_value=[]) as fetch:
        gap_repair._fetch_single_candle(
            exchange="bitfinex",
            symbol=symbol,
            timeframe="4h",
            open_time=datetime(2025, 12, 1, tzinfo=timezone.utc),
        )

    assert fetch.call_args.kwargs["symbol"] == f"t{symbol[:-3]}:USD"


@pytest.mark.parametrize("symbol", ["BTCUSD", "SOLUSD", "EOSUSD"])
def test_feeds_leave_concatenated_markets_alone(symbol: str) -> None:
    from datetime import datetime, timezone

    from core.market_data import bitfinex_backfill as backfill

    with patch.object(backfill, "_fetch_bitfinex_candles_page", return_value=[]) as fetch:
        list(
            backfill._iter_bitfinex_candles(
                exchange="bitfinex",
                symbol=symbol,
                timeframe="1h",
                start=datetime(2026, 1, 2, tzinfo=timezone.utc),
                end=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
        )

    assert fetch.call_args.kwargs["symbol"] == f"t{symbol}"
