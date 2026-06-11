FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY packages/domain /app/packages/domain
COPY backend/requirements.txt /app/backend/requirements.txt

RUN pip install --no-cache-dir /app/packages/domain \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/app /app/app
COPY backend/alembic /app/backend/alembic
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/scripts/start-dev.sh /app/backend/scripts/start-dev.sh

ENV PYTHONPATH=/app/packages/domain:/app

WORKDIR /app
CMD ["sh", "/app/backend/scripts/start-dev.sh"]
