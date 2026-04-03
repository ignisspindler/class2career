#!/usr/bin/env bash
# run-local.sh — Start Flask API locally for development and testing
# Usage: bash scripts/run-local.sh [port]
#
# Loads env vars from .env in the project root, then runs Flask on port 5000
# (or whatever port you pass as the first argument).

set -euo pipefail

PORT="${1:-5000}"
SITE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$SITE_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found."
  echo "Copy .env.example to .env and fill in your keys."
  exit 1
fi

# Export all vars from .env (skip blank lines and comments)
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export FLASK_APP="$SITE_DIR/api/index.py"
export FLASK_ENV=development
export SITE_URL="http://localhost:$PORT"

# Use venv if present, otherwise fall back to system python3
PYTHON="python3"
if [[ -f "$SITE_DIR/.venv/bin/python" ]]; then
  PYTHON="$SITE_DIR/.venv/bin/python"
fi

echo "=== Local Flask server ==="
echo "  URL  : http://localhost:$PORT"
echo "  Stats: http://localhost:$PORT/stats"
echo "  Env  : $ENV_FILE"
echo "  Python: $PYTHON"
echo ""

cd "$SITE_DIR"
"$PYTHON" -m flask run --port="$PORT" --host=127.0.0.1
