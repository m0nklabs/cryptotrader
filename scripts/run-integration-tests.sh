#!/usr/bin/env bash
# Run disposable PostgreSQL integration tests.
#
# Single command that:
# 1. Starts a disposable PostgreSQL container (if not running)
# 2. Applies schema.sql and all migration files
# 3. Runs the integration test suite
# 4. Cleans up the container
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

# Step 1: Stop existing container if clean start
if $CLEAN_START; then
    echo "[1/4] Stopping existing container..."
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
fi

# Step 2: Start disposable PostgreSQL
echo "[2/4] Starting disposable PostgreSQL..."
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "  Container already running: $CONTAINER_NAME"
elif docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "  Reusing existing container: $CONTAINER_NAME"
    docker start "$CONTAINER_NAME" > /dev/null
else
    docker run -d \
        --name "$CONTAINER_NAME" \
        -p "$INTEGRATION_PORT":5432 \
        -e "POSTGRES_USER=$INTEGRATION_USER" \
        -e "POSTGRES_PASSWORD=$INTEGRATION_PASS" \
        -e "POSTGRES_DB=$INTEGRATION_DB" \
        -e "POSTGRES_INITDB_ARGS=--encoding=UTF-8" \
        "postgres:$PG_VERSION" > /dev/null
fi

# Wait for PostgreSQL to be ready
echo "  Waiting for PostgreSQL to be ready..."
for i in $(seq 1 15); do
    if PGPASSWORD="$INTEGRATION_PASS" psql -h 127.0.0.1 -p "$INTEGRATION_PORT" -U "$INTEGRATION_USER" -d "$INTEGRATION_DB" -c "SELECT 1" > /dev/null 2>&1; then
        echo "  PostgreSQL is ready (port $INTEGRATION_PORT)"
        break
    fi
    if [ "$i" -eq 15 ]; then
        echo "ERROR: PostgreSQL did not become ready in time"
        docker logs "$CONTAINER_NAME" 2>/dev/null | tail -20
        docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

# Step 3: Apply schema and migrations
echo "[3/4] Applying schema and migrations..."
DB_URL="postgresql://${INTEGRATION_USER}:${INTEGRATION_PASS}@127.0.0.1:${INTEGRATION_PORT}/${INTEGRATION_DB}"
DISPLAY_DB_URL="postgresql://${INTEGRATION_USER}:***@127.0.0.1:${INTEGRATION_PORT}/${INTEGRATION_DB}"

# Apply main schema
PGPASSWORD="$INTEGRATION_PASS" psql -h 127.0.0.1 -p "$INTEGRATION_PORT" -U "$INTEGRATION_USER" -d "$INTEGRATION_DB" \
    -f "$PROJECT_ROOT/db/schema.sql" > /dev/null 2>&1
echo "  Schema applied"

# Apply migrations in order
MIGRATION_COUNT=0
for migration_file in $(ls "$PROJECT_ROOT/db/migrations/"*.sql | sort); do
    migration_name=$(basename "$migration_file")
    PGPASSWORD="$INTEGRATION_PASS" psql -h 127.0.0.1 -p "$INTEGRATION_PORT" -U "$INTEGRATION_USER" -d "$INTEGRATION_DB" \
        -f "$migration_file" > /dev/null 2>&1
    MIGRATION_COUNT=$((MIGRATION_COUNT + 1))
done
echo "  Migrations applied ($MIGRATION_COUNT files)"

# Step 4: Run integration tests
echo "[4/4] Running integration tests..."
cd "$PROJECT_ROOT"

# Set DATABASE_URL and PGPASSWORD for tests that read from env
export DATABASE_URL="$DB_URL"
export PGPASSWORD="$INTEGRATION_PASS"

# Run pytest with integration marker
"$PYTHON_BIN" -m pytest tests/integration/ -v \
    --tb=short \
    --durations=5 \
    "$@"

TEST_EXIT=$?

# Step 5: Cleanup
if $KEEP_CONTAINER; then
    echo ""
    echo "=== Tests complete (container kept) ==="
    echo "  Container: $CONTAINER_NAME"
    echo "  Port:      $INTEGRATION_PORT"
    echo "  Database:  $DISPLAY_DB_URL"
    echo "  To stop:   docker rm -f $CONTAINER_NAME"
else
    docker rm -f "$CONTAINER_NAME" > /dev/null 2>&1
    echo ""
    echo "=== Tests complete (container removed) ==="
fi

exit $TEST_EXIT
