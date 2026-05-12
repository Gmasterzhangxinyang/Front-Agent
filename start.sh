#!/bin/bash
# Railway sets $PORT to the exposed port
# uvicorn: internal 8000, streamlit: internal 8501, proxy: $PORT

UVICORN_PORT=8000
STREAMLIT_PORT=8501
PROXY_PORT=${PORT:-8080}

# Start uvicorn on internal port
uvicorn main:app --host 0.0.0.0 --port $UVICORN_PORT &
UVICORN_PID=$!

# Start streamlit on internal port
streamlit run app_ui.py --server.port $STREAMLIT_PORT --server.address 0.0.0.0 &
STREAMLIT_PID=$!

# Wait for services to be ready with a health check
echo "Waiting for services to be ready..."
for i in {1..30}; do
  if nc -z 127.0.0.1 $UVICORN_PORT 2>/dev/null && nc -z 127.0.0.1 $STREAMLIT_PORT 2>/dev/null; then
    echo "Services ready after $((i-1)) seconds"
    break
  fi
  sleep 1
done

# Start proxy — this runs in foreground on the Railway-exposed port
echo "Starting proxy on port $PROXY_PORT..."
python proxy.py $UVICORN_PORT $STREAMLIT_PORT $PROXY_PORT
