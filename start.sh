#!/bin/bash
# Railway sets $PORT — proxy listens on it, forwards to uvicorn:8000 and streamlit:8501

uvicorn main:app --host 127.0.0.1 --port 8000 &
UVICORN_PID=$!

streamlit run app_ui.py --server.port 8500 --server.address 127.0.0.1 &
STREAMLIT_PID=$!

sleep 5

exec python proxy.py 8000 8500 $PORT
