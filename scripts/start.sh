#!/usr/bin/env bash
# AFMX — Start server (auto-detects Python 3.10+)
# Usage: bash scripts/start.sh [--reload] [--port 8100] [--workers 4]
set -e

RELOAD=""
PORT="${AFMX_PORT:-8100}"
WORKERS="${AFMX_WORKERS:-1}"

for arg in "$@"; do
    case $arg in
        --reload) RELOAD="--reload" ;;
        --port=*) PORT="${arg#*=}" ;;
        --workers=*) WORKERS="${arg#*=}" ;;
    esac
done

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Verify Python version
python -c "
import sys
if sys.version_info < (3, 10):
    print(f'❌  Python 3.10+ required. Got: {sys.version}')
    sys.exit(1)
print(f'✅  Python {sys.version.split()[0]}')
"

echo "🚀  Starting AFMX on port $PORT (workers=$WORKERS $RELOAD)"
python -m uvicorn afmx.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info \
    $RELOAD
