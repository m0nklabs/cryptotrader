#!/usr/bin/env bash
# Run disposable PostgreSQL integration tests.
#
# Single command that delegates disposable PostgreSQL lifecycle to the pytest
# integration fixtures, then runs the integration test suite.
#
# Usage:
#   ./scripts/run-integration-tests.sh          # Run all integration tests
#   ./scripts/run-integration-tests.sh --help   # Show usage
#   ./scripts/run-integration-tests.sh --keep   # Keep container after tests
#   ./scripts/run-integration-tests.sh --clean  # Force clean restart
#
# Environment:
#   INTEGRATION_PORT  - Port for disposable DB (default: 5433)
#   INTEGRATION_DB    - Database name (default: cryptotrader_test)
#   INTEGRATION_USER  - Database user (default: cryptotrader)
#   INTEGRATION_PASS  - Database password (default: testpassword123)
#   PG_VERSION        - PostgreSQL image version (default: 16-alpine)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configuration
INTEGRATION_PORT="${INTEGRATION_PORT:-5433}"
INTEGRATION_DB="${INTEGRATION_DB:-cryptotrader_test}"
INTEGRATION_USER="${INTEGRATION_USER:-cryptotrader}"
INTEGRATION_PASS="${INTEGRATION_PASS:-testpassword123}"
PG_VERSION="${PG_VERSION:-16-alpine}"
CONTAINER_NAME="cryptotrader-test-db"
KEEP_CONTAINER=false
CLEAN_START=false
PSQL_CMD="psql -h 127.0.0.1 -p $INTEGRATION_PORT -U $INTEGRATION_USER -d $INTEGRATION_DB"
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "Usage: $0 [--keep] [--clean] [--help]"
            echo ""
            echo "Options:"
            echo "  --keep    Keep the PostgreSQL container after tests"
            echo "  --clean   Force stop and restart the container"
            echo "  --help    Show this help message"
            exit 0
            ;;
        --keep)  KEEP_CONTAINER=true; shift ;;
        --clean) CLEAN_START=true; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

echo "=== Cryptotrader Integration Tests ==="
echo "  Container: $CONTAINER_NAME"
echo "  Port:      $INTEGRATION_PORT"
echo "  Database:  $INTEGRATION_DB"
echo "  User:      $INTEGRATION_USER"
echo "  PG Image:  postgres:$PG_VERSION"
echo ""

DB_URL="postgresql://${INTEGRATION_USER}:${INTEGRATION_PASS}@127.0.0.1:${INTEGRATION_PORT}/${INTEGRATION_DB}"
DISPLAY_DB_URL="postgresql://${INTEGRATION_USER}:***@127.0.0.1:${INTEGRATION_PORT}/${INTEGRATION_DB}"

# Step 1: Run integration tests through the disposable DB fixtures
echo "[1/1] Running integration tests..."
cd "$PROJECT_ROOT"

# Pass disposable DB settings to the pytest fixtures.
export DATABASE_URL="$DB_URL"
export PGPASSWORD="$INTEGRATION_PASS"
export INTEGRATION_PORT
export INTEGRATION_DB
export INTEGRATION_USER
export INTEGRATION_PASS
export INTEGRATION_CONTAINER_NAME="$CONTAINER_NAME"
if $KEEP_CONTAINER; then
    export CRYPTOTRADER_KEEP_DISPOSABLE_DB=1
else
    export CRYPTOTRADER_KEEP_DISPOSABLE_DB=0
fi
if $CLEAN_START; then
    export CRYPTOTRADER_CLEAN_DISPOSABLE_DB=1
else
    export CRYPTOTRADER_CLEAN_DISPOSABLE_DB=0
fi

# Run pytest with integration marker
TEST_EXIT=0
"$PYTHON_BIN" -m pytest tests/integration/ -v \
    --tb=short \
    --durations=5 \
    "$@" || TEST_EXIT=$?

# Step 2: Cleanup
if $KEEP_CONTAINER; then
    echo ""
    echo "=== Tests complete (container kept) ==="
    echo "  Container: $CONTAINER_NAME"
    echo "  Port:      $INTEGRATION_PORT"
    echo "  Database:  $DISPLAY_DB_URL"
    echo "  To stop:   docker rm -f $CONTAINER_NAME"
else
    echo ""
    echo "=== Tests complete (container removed) ==="
fi

exit $TEST_EXIT
