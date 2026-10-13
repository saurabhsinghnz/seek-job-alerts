#!/bin/bash
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables from .env (if present) and export them
if [ -f "$SCRIPT_DIR/.env" ]; then
	# shellcheck disable=SC1091
	set -o allexport
	source "$SCRIPT_DIR/.env"
	set +o allexport
fi

# Use the standard setup environment first, then the checked-in project
# environment used by this workspace.
if [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
	PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
elif [ -x "$SCRIPT_DIR/seek-scraper/bin/python" ]; then
	PYTHON_BIN="$SCRIPT_DIR/seek-scraper/bin/python"
else
	PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c 'import playwright' >/dev/null 2>&1; then
	echo "Playwright is not installed in the selected Python environment." >&2
	echo "Run ./setup.sh or install requirements.txt in the active environment." >&2
	exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/seek_job_alert.py"
