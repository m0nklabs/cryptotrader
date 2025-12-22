#!/usr/bin/env python3
"""Initialize the optional database schema.

Runs the SQL in db/schema.sql against the database pointed to by DATABASE_URL.

Usage:
  python -m db.init_db

Requirements:
  - DATABASE_URL must be set
  - SQLAlchemy installed (see requirements.txt optional deps)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _iter_sql_statements(sql: str) -> Iterable[str]:
    """Split a SQL script into executable statements.

    Supports:
    - `--` line comments
    - quoted strings (single and double quotes)

    This is intentionally simple and designed for our schema.sql (no $$ quoting).
    """

    buf: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]

        # Handle -- comments (only when not in quotes)
        if not in_single and not in_double and ch == "-" and i + 1 < len(sql) and sql[i + 1] == "-":
            # Skip until end of line
            while i < len(sql) and sql[i] not in ("\n", "\r"):
                i += 1
            continue

        if ch == "'" and not in_double:
            # Toggle single quote state unless escaped by doubling ''
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            buf = []
            if stmt:
                yield stmt
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        yield tail


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    try:
        from sqlalchemy import create_engine  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "SQLAlchemy is required to run db init. Install optional deps: pip install SQLAlchemy psycopg2-binary"
        ) from exc

    schema_path = Path(__file__).resolve().parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    engine = create_engine(database_url, echo=False)

    # Execute schema as individual statements to stay driver-agnostic.
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for stmt in _iter_sql_statements(schema_sql):
            cur.execute(stmt)
        raw.commit()
    finally:
        try:
            raw.close()
        except Exception:
            pass

    print("✅ Database schema applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
