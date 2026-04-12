#!/bin/bash
set -e

# Load environment variables from .env (if present) and export them
if [ -f ".env" ]; then
	# shellcheck disable=SC1091
	set -o allexport
	source .env
	set +o allexport
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
	# shellcheck disable=SC1091
	source venv/bin/activate
fi

python seek_job_alert.py
