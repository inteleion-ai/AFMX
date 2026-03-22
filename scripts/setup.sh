#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AFMX — Oracle Cloud / Linux deployment script
# Run this once to set up the environment correctly on Python 3.10+
# Usage: bash scripts/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        VERSION=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌  Python 3.10+ not found."
    echo "   Install with: sudo dnf install python3.10  (Oracle Linux)"
    echo "              or: sudo apt install python3.10  (Ubuntu/Debian)"
    exit 1
fi

echo "✅  Using: $PYTHON ($($PYTHON --version))"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "→  Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

# Activate
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip --quiet

# Install package in editable mode with dev dependencies
echo "→  Installing AFMX..."
pip install -e ".[dev]" --quiet

echo ""
echo "✅  AFMX installed successfully!"
echo ""
echo "   Start the server:"
echo "     source .venv/bin/activate"
echo "     afmx serve --reload"
echo "     # OR"
echo "     python -m afmx serve --reload"
echo ""
echo "   Run tests:"
echo "     pytest tests/ -v"
echo ""
