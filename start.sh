#!/bin/bash
# Railway sets $PORT — uvicorn:8000, streamlit:8500, proxy:$PORT
uvicorn main:app --host 127.0.0.1 --port 8000 &
streamlit run app_ui.py --server.port 8500 --server.address 127.0.0.1 &
sleep 15
exec python proxy.py 8000 8500 $PORT
