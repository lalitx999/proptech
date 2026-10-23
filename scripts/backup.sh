#!/usr/bin/env bash
# ==============================================================================
# PropTech Automated Database & Media Backup Script
# Usage in crontab (daily at 03:00):
# 0 3 * * * /path/to/proptech/scripts/backup.sh >> /var/log/proptech_backup.log 2>&1
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DATE="$(date +%Y-%m-%d)"
BACKUP_DIR="${PROJECT_ROOT}/backups/${BACKUP_DATE}"

# Load environment variables if .env.prod exists
if [ -f "${PROJECT_ROOT}/.env.prod" ]; then
    # shellcheck disable=SC1091
    export $(grep -v '^#' "${PROJECT_ROOT}/.env.prod" | xargs)
elif [ -f "${PROJECT_ROOT}/.env" ]; then
    # shellcheck disable=SC1091
    export $(grep -v '^#' "${PROJECT_ROOT}/.env" | xargs)
fi

DB_USER="${DB_USER:-proptech_user}"
DB_NAME="${DB_NAME:-proptech_db}"
CONTAINER_NAME="proptech_postgres"

mkdir -p "${BACKUP_DIR}"

send_telegram_alert() {
    local msg="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=🚨 [PropTech Backup Alert] ${msg}" >/dev/null 2>&1 || true
    fi
}

echo "[$TIMESTAMP] Starting automated backup..."

# 1. PostgreSQL Database Dump (Custom Compressed format)
DB_DUMP_FILE="${BACKUP_DIR}/db_${DB_NAME}_${TIMESTAMP}.dump"
if docker exec "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" -Fc "${DB_NAME}" > "${DB_DUMP_FILE}"; then
    DUMP_SIZE="$(du -h "${DB_DUMP_FILE}" | cut -f1)"
    echo "[$TIMESTAMP] Database dumped successfully: ${DB_DUMP_FILE} (${DUMP_SIZE})"
else
    echo "[$TIMESTAMP] ERROR: Database dump failed!" >&2
    send_telegram_alert "Database backup failed on $(hostname) at ${TIMESTAMP}!"
    exit 1
fi

# 2. Media Directory Backup (Gzipped Tarball)
MEDIA_TAR_FILE="${BACKUP_DIR}/media_${TIMESTAMP}.tar.gz"
if [ -d "${PROJECT_ROOT}/media" ]; then
    tar -czf "${MEDIA_TAR_FILE}" -C "${PROJECT_ROOT}" media
    MEDIA_SIZE="$(du -h "${MEDIA_TAR_FILE}" | cut -f1)"
    echo "[$TIMESTAMP] Media files backed up: ${MEDIA_TAR_FILE} (${MEDIA_SIZE})"
fi

# 3. Retention Cleanup (Keep 14 days of backups)
echo "[$TIMESTAMP] Cleaning up backups older than 14 days..."
find "${PROJECT_ROOT}/backups" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null || true

echo "[$TIMESTAMP] Backup completed successfully!"
