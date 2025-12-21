from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from core.types import OrderIntent


@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    reason: str


class SafetyCheck(Protocol):
    def check(self, *, intent: OrderIntent) -> SafetyResult:
        """Return whether intent is safe to execute."""


def run_safety_checks(*, checks: Sequence[SafetyCheck], intent: OrderIntent) -> SafetyResult:
    for check in checks:
        res = check.check(intent=intent)
        if not res.ok:
            return res
    return SafetyResult(ok=True, reason="ok")
