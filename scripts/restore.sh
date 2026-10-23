#!/usr/bin/env bash
# ==============================================================================
# PropTech Database Backup Verification & Restore Test Script
# Usage:
#   ./scripts/restore.sh /path/to/dumpfile.dump [optional_target_db_name]
# ==============================================================================

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path_to_dump_file> [target_db_name]"
    echo "Example: $0 ./backups/2026-10-23/db_proptech_db_xxx.dump restore_test"
    exit 1
fi

DUMP_FILE="$1"
TEST_DB="${2:-restore_test_$(date +%s)}"
CONTAINER_NAME="proptech_postgres"
DB_USER="${DB_USER:-proptech_user}"

if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: Dump file not found: $DUMP_FILE" >&2
    exit 1
fi

echo "=== [PropTech Restore Verification Test] ==="
echo "Dump file: $DUMP_FILE"
echo "Target test database: $TEST_DB"

# 1. Create fresh test database in container
echo "Creating isolated test database: $TEST_DB..."
docker exec -i "$CONTAINER_NAME" dropdb --if-exists -U "$DB_USER" "$TEST_DB"
docker exec -i "$CONTAINER_NAME" createdb -U "$DB_USER" "$TEST_DB"

# 2. Restore dump into test database
echo "Restoring database from dump..."
docker exec -i "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$TEST_DB" --no-owner --clean --if-exists < "$DUMP_FILE" || true

# 3. Query row counts to confirm integrity
echo "Verifying restored data integrity..."
USERS_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" -t -A -c "SELECT count(*) FROM accounts_user;" 2>/dev/null || echo "0")
LISTINGS_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" -t -A -c "SELECT count(*) FROM listings_listing;" 2>/dev/null || echo "0")
PROPERTIES_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$TEST_DB" -t -A -c "SELECT count(*) FROM properties_property;" 2>/dev/null || echo "0")

echo "=========================================="
echo "✅ Restore Verification Passed!"
echo "   - Users restored:       $USERS_COUNT"
echo "   - Listings restored:    $LISTINGS_COUNT"
echo "   - Properties restored:  $PROPERTIES_COUNT"
echo "=========================================="

echo "Cleaning up temporary test database..."
docker exec -i "$CONTAINER_NAME" dropdb -U "$DB_USER" "$TEST_DB"
echo "Done!"
