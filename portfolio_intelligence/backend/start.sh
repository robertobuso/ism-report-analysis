#!/bin/bash
set -ex  # Exit on error and print commands

echo "===== Starting Portfolio Intelligence API ====="
echo "PORT=${PORT:-8000}"
echo "DATABASE_URL=${DATABASE_URL:0:30}..."

echo "===== Running database migrations ====="
alembic upgrade head || { echo "MIGRATION FAILED"; exit 1; }
echo "===== Migrations complete! ====="

echo "===== Starting uvicorn on port ${PORT:-8000} ====="
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
