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

# Wait for services to be ready
sleep 10

# Start proxy — this runs in foreground on the Railway-exposed port
exec python proxy.py $UVICORN_PORT $STREAMLIT_PORT $PROXY_PORT