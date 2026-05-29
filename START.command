#!/bin/bash
cd "$(dirname "$0")"

# Find non-system Python
PYTHON=""
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.12; do
  if [ -x "$p" ]; then
    PYTHON="$p"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "No Python found. Install via: brew install python3"
  read -p "Press Enter to close..."
  exit 1
fi

# Create venv if needed
if [ ! -d ".venv" ]; then
  echo "Setting up virtual environment..."
  "$PYTHON" -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/playwright install chromium
fi

# Kill anything on port 5050
lsof -ti:5050 | xargs kill -9 2>/dev/null || true

echo ""
echo "Starting Halfway Charge Analytics..."
echo "Open: http://localhost:5050"
echo ""
open "http://localhost:5050"
.venv/bin/python app.py
