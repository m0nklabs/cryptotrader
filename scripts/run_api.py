#!/usr/bin/env python3
"""Run the FastAPI read-only API server.

This script starts the uvicorn server for the minimal read-only API.

Usage:
    python scripts/run_api.py [--host HOST] [--port PORT]

Environment:
    DATABASE_URL - Required. PostgreSQL connection string.

Examples:
    python scripts/run_api.py
    python scripts/run_api.py --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure imports work when invoked as a script
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    """Run the API server."""
    parser = argparse.ArgumentParser(
        description="Run the FastAPI read-only API server for candles and health endpoints."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    # Check DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable is required", file=sys.stderr)
        print("See .env.example for configuration", file=sys.stderr)
        return 1

    print(f"Starting FastAPI server on {args.host}:{args.port}")
    print("Endpoints:")
    print(f"  - GET http://{args.host}:{args.port}/health")
    print(f"  - GET http://{args.host}:{args.port}/candles/latest")
    print()

    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is not installed", file=sys.stderr)
        print("Install with: pip install -r requirements.txt", file=sys.stderr)
        return 1

    # Run the server
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
