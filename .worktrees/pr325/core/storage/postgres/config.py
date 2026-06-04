from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresConfig:
    """Connection configuration.

    `database_url` should come from environment (e.g. DATABASE_URL).
    Do not log it.
    """

    database_url: str
