#!/bin/bash
# Railway sets $PORT to the exposed port (e.g. 8080)
# We start uvicorn on PORT, streamlit on 8501, and a reverse proxy on 8080

APP_PORT=${PORT:-8080}

# Start uvicorn in background
uvicorn main:app --host 0.0.0.0 --port $APP_PORT &
UVICORN_PID=$!

# Start streamlit in background
streamlit run app_ui.py --server.port 8501 --server.address 0.0.0.0 &
STREAMLIT_PID=$!

# Start reverse proxy in background
python proxy.py $APP_PORT &
PROXY_PID=$!

# Wait for all
wait $UVICORN_PID $STREAMLIT_PID $PROXY_PID
