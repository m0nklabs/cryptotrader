from pathlib import Path
import sys

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


def test_backfill_and_gap_repair_share_the_same_translation() -> None:
    """Both feeds must agree, or one of them silently writes nothing."""
    from core.market_data import bitfinex_backfill, bitfinex_gap_repair

    for symbol in CONCAT_FORM_SYMBOLS + COLON_FORM_SYMBOLS:
        expected = normalize_bitfinex_symbol(symbol)
        assert bitfinex_backfill.normalize_bitfinex_symbol(symbol) == expected
        assert bitfinex_gap_repair.normalize_bitfinex_symbol(symbol) == expected
