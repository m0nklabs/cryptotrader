#!/bin/bash
set -e

# This script initializes the database schema on first container start
# It's executed by postgres:16-alpine's entrypoint

echo "Initializing cryptotrader database schema..."

# Apply schema if schema.sql exists
if [ -f /docker-entrypoint-initdb.d/schema.sql ]; then
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/schema.sql
    echo "Schema applied successfully"
else
    echo "Warning: schema.sql not found, skipping schema initialization"
fi

echo "Database initialization complete"
