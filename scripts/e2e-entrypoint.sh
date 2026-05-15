#!/bin/sh
set -e

echo "=== E2E: Running database migrations ==="
flask db upgrade

echo "=== E2E: Seeding test data ==="
python scripts/seed_dev.py

echo "=== E2E: Starting Flask dev server ==="
exec "$@"
