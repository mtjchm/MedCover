#!/bin/sh
set -e

echo "Running database migrations..."
flask db upgrade

echo "Verifying database schema..."
flask verify-schema

echo "Starting application..."
exec "$@"
