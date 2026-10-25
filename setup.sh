#!/bin/bash
# Quick setup script for Seek Job Alert Bot

set -e

echo "🚀 Setting up Seek Job Alert Bot..."
echo ""

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python_works_with_subprocesses() {
    if [ -z "$PYTHON_BIN" ]; then
        "$1" -c 'import subprocess, sys; subprocess.run([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)' >/dev/null 2>&1
        return
    fi
    "$PYTHON_BIN" -c 'import subprocess, sys; probe = """import subprocess, sys; subprocess.run([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)"""; result = subprocess.run([sys.argv[1], "-c", probe], stdout=subprocess.PIPE, stderr=subprocess.PIPE); sys.exit(result.returncode != 0)' "$1" >/dev/null 2>&1
}

# Prefer Homebrew Python, then PATH/system Python, while rejecting broken runtimes.
PYTHON_BIN=""
for candidate in /opt/homebrew/bin/python3 "$(command -v python3 2>/dev/null)" /usr/bin/python3; do
    if [ -n "$candidate" ] && [ -x "$candidate" ] && python_works_with_subprocesses "$candidate"; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ No Python 3 interpreter with working subprocess support was found" >&2
    exit 1
fi

echo "✅ Using $($PYTHON_BIN --version 2>&1)"
echo ""

# Keep a broken existing venv intact and build a replacement alongside it.
VENV_DIR="venv"
if [ -x "$VENV_DIR/bin/python" ] && ! python_works_with_subprocesses "$VENV_DIR/bin/python"; then
    VENV_DIR=".venv"
    echo "⚠️  Existing venv cannot launch subprocesses; using .venv instead"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
    if ! python_works_with_subprocesses "$VENV_DIR/bin/python"; then
        echo "❌ $VENV_DIR also has a broken Python runtime; move it aside and rerun ./setup.sh" >&2
        exit 1
    fi
    echo "✅ Virtual environment already exists: $VENV_DIR"
else
    echo "📦 Creating virtual environment: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$SCRIPT_DIR/$VENV_DIR/bin/python"

# Install dependencies
echo ""
echo "📚 Installing dependencies..."
"$VENV_PYTHON" -m pip install -q -r requirements.txt
echo "✅ Dependencies installed"

# Install the browser required by Playwright
echo "🌐 Installing Playwright Chromium..."
"$VENV_PYTHON" -m playwright install chromium
echo "✅ Playwright Chromium installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your Telegram credentials"
    echo ""
    echo "To get credentials:"
    echo "  1. Bot Token: Talk to @BotFather on Telegram"
    echo "  2. Chat ID: Talk to @userinfobot on Telegram"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Verify .env has your Telegram credentials"
echo "  2. Run: ./run.sh"
echo ""
