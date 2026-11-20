"""Translation of internal market symbols to Bitfinex candle API symbols.

Internal (database, config, env-file) symbols are concatenated, e.g. ``AVAXUSD``.
The candles endpoint, however, does not accept that shape for every market: some
markets only exist colon-separated (``tAVAX:USD``), others only concatenated
(``tBTCUSD``), and the wrong shape answers with ``[]`` instead of an error.

The authoritative source for which shape a market uses is the exchange's own
published pair list, ``/v2/conf/pub:list:pair:exchange``. The two sets derived
from it are disjoint, so a base is listed in at most one of them.
"""

from __future__ import annotations

# Bases whose USD market is colon-separated on Bitfinex (``tAVAX:USD``).
# Snapshot of `/v2/conf/pub:list:pair:exchange`; every other base uses the
# concatenated form that this module preserves by default.
_COLON_FORM_USD_BASES = frozenset(
    {
        "AAVE",
        "ALKN",
        "ALT2612",
        "AVAX",
        "BCHN",
        "BMN2",
        "CALCPB",
        "CELO",
        "CH100",
        "CMSTR",
        "CMTPL",
        "DOGE",
        "ETH2X",
        "EURQ",
        "EURR",
        "GOMINING",
        "HYPE",
        "KAIA",
        "LIFIII",
        "LINK",
        "MXNT",
        "NEAR",
        "PEPE",
        "SHIB",
        "STABLE",
        "STRCST",
        "TITAN1",
        "TITAN2",
        "TITAN4",
        "USAT",
        "USDF",
        "USDQ",
        "USDR",
        "USTBL",
        "WHBT",
        "XAUT",
    }
)

_QUOTE = "USD"


def normalize_bitfinex_symbol(symbol: str) -> str:
    """Return the Bitfinex candles-API symbol for an internal market symbol.

    ``BTCUSD`` -> ``tBTCUSD``, ``AVAXUSD`` -> ``tAVAX:USD``. Database identity is
    never changed here: only the symbol used in the API request is rewritten, so
    stored candles keep the internal (concatenated) symbol.

    A value that already starts with ``t`` is treated as a complete API symbol and
    returned verbatim, because stripping that prefix would corrupt bases that
    themselves start with ``t`` (``tTRXUSD``). Callers pass internal symbols.
    """

    s = symbol.strip()
    if not s:
        raise ValueError("symbol is required")
    if s.startswith("t"):
        return s

    base, sep, quote = s.partition(":")
    if not sep:
        base, quote = s, ""
    if quote:
        return f"t{base}:{quote}"
    if s.endswith(_QUOTE) and s[: -len(_QUOTE)] in _COLON_FORM_USD_BASES:
        return f"t{s[: -len(_QUOTE)]}:{_QUOTE}"
    return f"t{s}"
