from decimal import Decimal

import pytest

from api.routes.dossier import _as_float


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1.23"), 1.23),
        (2, 2.0),
        (2.5, 2.5),
        ("3.14", 3.14),
        # float() trims leading/trailing whitespace.
        (" 3.14 ", 3.14),
        (None, None),
        ("invalid", None),
    ],
)
def test_as_float_handles_numeric_inputs(value, expected) -> None:
    result = _as_float(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)
