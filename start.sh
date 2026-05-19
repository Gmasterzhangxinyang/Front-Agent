#!/bin/bash
# Startup: run Streamlit UI (port 8500) and Uvicorn API (port 8080) concurrently

# Kill any existing processes
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "streamlit run" 2>/dev/null || true

sleep 1

# Start Streamlit in the background on port 8500
streamlit run app_ui.py --server.port 8500 --server.address 0.0.0.0 &

# Start Uvicorn in the foreground on $PORT (Railway routes here, default 8080)
exec uvicorn main:app --host 0.0.0.0 --port $PORT