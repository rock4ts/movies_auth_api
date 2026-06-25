#!/bin/bash
set -euo pipefail

if [ "${APP_MODE:-prod}" != "dev" ]; then
  alembic upgrade head

  python -m app.commands.create_default_role
  python -m app.commands.create_superuser \
    --email "${SUPERUSER_EMAIL}" \
    --password "${SUPERUSER_PASSWORD}"
fi

exec gunicorn \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  app.main:app \
  --bind 0.0.0.0:8000
