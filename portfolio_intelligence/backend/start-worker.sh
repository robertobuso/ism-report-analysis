#!/bin/bash
set -ex  # Exit on error and print commands

echo "===== Starting Portfolio Intelligence Celery Worker ====="
echo "REDIS_URL=${REDIS_URL:0:30}..."
echo "DATABASE_URL=${DATABASE_URL:0:30}..."

echo "===== Starting Celery worker ====="
exec celery -A app.worker worker --loglevel=info --concurrency=2
