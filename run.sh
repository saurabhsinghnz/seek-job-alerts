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

PYTHON_BIN=""
for candidate in \
	"$SCRIPT_DIR/.venv/bin/python" \
	"$SCRIPT_DIR/venv/bin/python" \
	"$SCRIPT_DIR/seek-scraper/bin/python" \
	"$(command -v python3 2>/dev/null || command -v python 2>/dev/null)"; do
	if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
		continue
	fi
	if "$candidate" -c 'import subprocess, sys; subprocess.run([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)' >/dev/null 2>&1 \
		&& "$candidate" -c 'import playwright' >/dev/null 2>&1; then
		PYTHON_BIN="$candidate"
		break
	fi
done

if [ -z "$PYTHON_BIN" ]; then
	echo "No usable Python environment with Playwright was found." >&2
	echo "Run ./setup.sh to create one with a Python runtime that supports subprocesses." >&2
	exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/seek_job_alert.py"
