#!/bin/bash
cd "$(dirname "$0")"

echo "=== Halfway Charge Analytics ==="
echo ""

# Find a real Python (Homebrew or python.org installs avoid xcode-select)
PYTHON=""
for candidate in \
  /opt/homebrew/bin/python3 \
  /usr/local/bin/python3 \
  "$HOME/Library/Python/3.12/bin/python3" \
  "$HOME/Library/Python/3.11/bin/python3" \
  "$HOME/Library/Python/3.10/bin/python3"; do
  if [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done

# Fall back to PATH python3 only if it's not the macOS stub
if [ -z "$PYTHON" ] && command -v python3 &>/dev/null; then
  # macOS stub lives at /usr/bin/python3 and needs xcode — skip it
  PY_PATH="$(command -v python3)"
  if [ "$PY_PATH" != "/usr/bin/python3" ]; then
    PYTHON="$PY_PATH"
  fi
fi

if [ -z "$PYTHON" ]; then
  echo "ERROR: No usable Python 3 found."
  echo ""
  echo "Please install Python from https://www.python.org/downloads/"
  echo "or run:  brew install python3"
  echo ""
  read -p "Press Enter to exit..."
  exit 1
fi

echo "Using Python: $PYTHON"

# Set up venv
VENV_DIR=".venv"
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Setting up environment (first run only)..."
  "$PYTHON" -m venv "$VENV_DIR"
  if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "ERROR: Could not create virtual environment."
    read -p "Press Enter to exit..."
    exit 1
  fi
fi

source "$VENV_DIR/bin/activate"

# Install dependencies
if ! python3 -c "import flask" 2>/dev/null; then
  echo "Installing dependencies (first run only)..."
  python3 -m pip install -r requirements.txt -q
  python3 -m playwright install chromium 2>/dev/null || true
fi

echo "Starting Halfway Charge Analytics..."
echo "Opening http://localhost:5050 in your browser..."
echo "Press Ctrl+C to stop the app."
echo ""
python3 app.py
