#!/bin/bash
# Simple startup: load env vars then uvicorn on the port Railway exposes
# No Streamlit UI - only email handling logic

# Load .env file if it exists (for local development)
if [ -f "$(dirname "$0")/.env" ]; then
  set -a
  source "$(dirname "$0")/.env"
  set +a
fi

# Kill any existing processes
pkill -f "uvicorn main:app" 2>/dev/null || true

sleep 1

# Start uvicorn on $PORT (Railway) or default 8000 (local)
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --reload