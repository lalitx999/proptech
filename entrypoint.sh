#!/bin/sh
set -e

echo "=== [PropTech Production Entrypoint] ==="

# Wait for DB readiness if host/port provided
if [ -n "$DB_HOST" ]; then
    echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}..."
    until python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$DB_HOST', int('${DB_PORT:-5432}')))
    s.close()
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
        sleep 1
    done
    echo "Database is ready!"
fi

# Run pending database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Ensure database cache table exists
echo "Ensuring cache table exists..."
python manage.py createcachetable >/dev/null 2>&1 || true

# Collect static assets into staticfiles/
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run production deployment check if running in production
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.prod" ]; then
    echo "Running production deployment verification..."
    python manage.py check --deploy
fi

echo "=== Starting application server ==="
exec "$@"
