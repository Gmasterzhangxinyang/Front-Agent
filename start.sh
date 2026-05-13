#!/bin/bash
# uvicorn: 8001, streamlit: 8500, proxy: 8001 (same as uvicorn - Railway routes here)

# Kill any existing processes on these ports
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "streamlit run" 2>/dev/null || true
pkill -f "proxy.py" 2>/dev/null || true

# Small delay to ensure ports are freed
sleep 2

# Start uvicorn in background
uvicorn main:app --host 127.0.0.1 --port 8001 &
UVICORN_PID=$!

# Start streamlit in background
streamlit run app_ui.py --server.port 8500 --server.address 127.0.0.1 &
STREAMLIT_PID=$!

# Wait for uvicorn to be ready (check that it's listening on 8001)
echo "Waiting for uvicorn to start..."
for i in $(seq 1 15); do
    if curl -s -o /dev/null http://127.0.0.1:8001/health 2>/dev/null; then
        echo "uvicorn is ready"
        break
    fi
    sleep 1
done

# Wait for streamlit to be ready
echo "Waiting for streamlit to start..."
for i in $(seq 1 15); do
    if curl -s -o /dev/null http://127.0.0.1:8500 2>/dev/null; then
        echo "streamlit is ready"
        break
    fi
    sleep 1
done

# Now safe to start proxy (uvicorn is already bound to 8001)
exec python proxy.py 8001 8500