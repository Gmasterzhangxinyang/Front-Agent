#!/bin/bash
# uvicorn: 8001, streamlit: 8500, proxy: 8001 (Railway routes here)

LOCKFILE="/tmp/start.lock"
PIDFILE="/tmp/start.pid"

# Prevent multiple instances - critical for Railway's health checks
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && [ "$OLD_PID" != "$$" ]; then
        # Check if it's still running
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo "Another start.sh instance running (PID $OLD_PID), exiting"
            exit 0
        else
            echo "Stale PID file removed (old PID: $OLD_PID)"
        fi
    fi
fi
echo $$ > "$PIDFILE"

cleanup() {
    rm -f "$PIDFILE" "$LOCKFILE"
}
trap cleanup EXIT INT TERM

# Kill existing processes on these ports FIRST
echo "Killing existing processes..."
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "streamlit run" 2>/dev/null || true
pkill -f "proxy.py" 2>/dev/null || true

# Wait for ports to be freed
sleep 3

# Check what's on port 8001
if netstat -tuln 2>/dev/null | grep -q ":8001 " || ss -tuln 2>/dev/null | grep -q ":8001 "; then
    echo "WARNING: Port 8001 still in use, will retry..."
    sleep 2
fi

# Start uvicorn in background
echo "Starting uvicorn..."
uvicorn main:app --host 127.0.0.1 --port 8001 &
UVICORN_PID=$!
echo "uvicorn started with PID $UVICORN_PID"

# Start streamlit in background
echo "Starting streamlit..."
streamlit run app_ui.py --server.port 8500 --server.address 127.0.0.1 &
STREAMLIT_PID=$!
echo "streamlit started with PID $STREAMLIT_PID"

# Wait for uvicorn to be ready
echo "Waiting for uvicorn to start..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null http://127.0.0.1:8001/health 2>/dev/null; then
        echo "uvicorn is ready (attempt $i)"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: uvicorn failed to start after 30 attempts"
        exit 1
    fi
    sleep 1
done

# Wait for streamlit to be ready
echo "Waiting for streamlit to start..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null http://127.0.0.1:8500 2>/dev/null; then
        echo "streamlit is ready (attempt $i)"
        break
    fi
    sleep 1
done

# Final check - is proxy already running?
if pgrep -f "proxy.py" > /dev/null; then
    echo "Proxy already running, exiting"
    exit 0
fi

echo "Starting proxy..."
exec python proxy.py 8001 8500