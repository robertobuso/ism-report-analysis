#!/bin/bash
set -e

echo "===== Starting Portfolio Intelligence Celery Worker with Health Check ====="

# Start health check HTTP server in background
python3 /app/healthcheck_server.py &
HTTP_PID=$!

echo "Health check server started on port 8000 (PID: $HTTP_PID)"

# Start Celery worker (this will run in foreground)
exec celery -A app.worker worker --loglevel=info --concurrency=2
