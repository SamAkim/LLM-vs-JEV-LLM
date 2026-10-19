#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Load .env if present
if [ -f .env ]; then set -a; . ./.env; set +a; fi

python3 -m pip install -q -r requirements.txt --break-system-packages 2>/dev/null \
  || python3 -m pip install -q -r requirements.txt

echo "Open http://localhost:8000  (Ctrl+C to stop)"
exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
