#!/bin/bash
# Simple startup: just uvicorn on the port Railway exposes
# No Streamlit UI - only email handling logic

# Kill any existing processes
pkill -f "uvicorn main:app" 2>/dev/null || true

sleep 1

# Start uvicorn directly on $PORT (Railway routes here)
exec uvicorn main:app --host 0.0.0.0 --port $PORT