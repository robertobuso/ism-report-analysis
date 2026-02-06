FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Shell form CMD allows && and env var expansion
CMD echo "Starting migrations..." && \
    alembic upgrade head && \
    echo "Migrations complete. Starting uvicorn on port ${PORT:-8000}..." && \
    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
