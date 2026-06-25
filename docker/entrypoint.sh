#!/bin/sh
set -eu

ROLE="${1:-web}"
APP_PORT="${PORT:-8000}"

echo "Starting role: ${ROLE}"

wait_for_postgres() {
  if [ -z "${DATABASE_URL:-}" ] && [ -z "${DB_HOST:-}" ]; then
    return 0
  fi

  echo "Waiting for PostgreSQL..."
  until python - <<'PY'
import os
from urllib.parse import urlparse

import psycopg

database_url = os.getenv("DATABASE_URL", "").strip()
if database_url:
    parsed = urlparse(database_url)
    conn = psycopg.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username or "",
        password=parsed.password or "",
        host=parsed.hostname or "",
        port=parsed.port or 5432,
    )
else:
    conn = psycopg.connect(
        dbname=os.getenv("DB_NAME", "escrow_project"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432"),
    )
conn.close()
PY
  do
    sleep 2
  done
}

wait_for_redis() {
  if [ -z "${REDIS_URL:-}" ] && [ -z "${REDIS_HOST:-}" ]; then
    return 0
  fi

  echo "Waiting for Redis..."
  until python - <<'PY'
import os
from urllib.parse import urlparse

import redis

redis_url = os.getenv("REDIS_URL", "").strip()
if redis_url:
    client = redis.Redis.from_url(redis_url)
else:
    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        username=os.getenv("REDIS_USERNAME") or None,
        password=os.getenv("REDIS_PASSWORD") or None,
    )
client.ping()
PY
  do
    sleep 2
  done
}

wait_for_postgres
wait_for_redis

if [ "${ROLE}" = "web" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  exec daphne -b 0.0.0.0 -p "${APP_PORT}" core.asgi:application
fi

if [ "${ROLE}" = "celery-worker" ]; then
  exec celery -A core worker -l "${CELERY_LOG_LEVEL:-info}" --concurrency="${CELERY_WORKER_CONCURRENCY:-2}"
fi

if [ "${ROLE}" = "celery-beat" ]; then
  exec celery -A core beat -l "${CELERY_LOG_LEVEL:-info}"
fi

echo "Unknown role: ${ROLE}" >&2
exit 1
