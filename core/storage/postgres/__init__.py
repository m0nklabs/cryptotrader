"""PostgreSQL storage skeleton.

This package intentionally provides structure only.
Concrete SQL implementation is delegated work.

Notes
- We avoid logging connection URLs to prevent accidental secret leakage.
- Implementations should default to read-only / dry-run behavior where relevant.
"""

from .config import PostgresConfig
from .stores import PostgresStores
