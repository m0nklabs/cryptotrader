#!/usr/bin/env python3
"""Apply database migrations.

Runs migration SQL files from db/migrations/ in order.

Usage:
  python -m scripts.apply_migrations [migration_file]
  
If migration_file is specified, only that file is applied.
Otherwise, all migrations are applied in order.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def apply_migration(migration_path: Path, engine) -> None:
    """Apply a single migration file."""
    print(f"Applying migration: {migration_path.name}")
    
    sql = migration_path.read_text(encoding="utf-8")
    
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(sql)
        raw.commit()
        print(f"✅ Migration {migration_path.name} applied successfully")
    except Exception as e:
        raw.rollback()
        print(f"❌ Migration {migration_path.name} failed: {e}")
        raise
    finally:
        try:
            raw.close()
        except Exception:
            pass


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL is not set")
        return 1

    try:
        from sqlalchemy import create_engine  # type: ignore
    except Exception as exc:
        print(f"❌ SQLAlchemy is required: {exc}")
        return 1

    # Convert asyncpg URL to psycopg2 for sync operations
    if "+asyncpg://" in database_url:
        database_url = database_url.replace("+asyncpg://", "+psycopg2://", 1)

    engine = create_engine(database_url, echo=False)

    migrations_dir = Path(__file__).resolve().parent.parent / "db" / "migrations"
    
    if len(sys.argv) > 1:
        # Apply specific migration
        migration_file = sys.argv[1]
        migration_path = migrations_dir / migration_file
        if not migration_path.exists():
            print(f"❌ Migration file not found: {migration_path}")
            return 1
        apply_migration(migration_path, engine)
    else:
        # Apply all migrations in order
        migration_files = sorted(migrations_dir.glob("*.sql"))
        if not migration_files:
            print("No migrations found")
            return 0
        
        for migration_path in migration_files:
            apply_migration(migration_path, engine)
    
    print("\n✅ All migrations applied successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
