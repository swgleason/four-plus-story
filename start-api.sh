#!/usr/bin/env bash
set -e

# Navigate to the API directory if the script is run from the monorepo root
# (Adjust this path if your script lives elsewhere)
cd "$(dirname "$0")/apps/api"

# Check for a virtual environment and activate it
if [ -d ".venv" ]; then
    echo "Activating virtual environment (.venv)..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "Activating virtual environment (venv)..."
    source venv/bin/activate
else
    echo "Error: No virtual environment found (.venv or venv) inside apps/api." >&2
    exit 1
fi

# Verify uvicorn is available
if ! command -v uvicorn &> /dev/null; then
    echo "Error: uvicorn could not be found. Did you run poetry/pip install?" >&2
    exit 1
fi

echo "Starting FastAPI server on port 8000..."
uvicorn app.main:app --reload --port 8000