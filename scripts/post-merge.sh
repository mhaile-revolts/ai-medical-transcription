#!/usr/bin/env bash
set -euo pipefail

python -m pip install \
  --disable-pip-version-check \
  --no-input \
  --upgrade \
  --target ".pythonlibs/lib/python$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages" \
  -r requirements.txt
npm ci --no-audit --no-fund --prefix src/frontend/web
npm run build --prefix src/frontend/web

if [[ "${APP_MODE:-demo}" != "demo" ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required when APP_MODE is not demo" >&2
    exit 1
  fi
  python -m alembic upgrade head
fi