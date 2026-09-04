#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  if [[ -n "${backend_pid:-}" ]]; then
    kill "$backend_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cd src/frontend/web
exec npm run dev