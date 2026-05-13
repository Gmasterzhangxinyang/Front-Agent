#!/bin/bash
# uvicorn: 8001, streamlit: 8500, proxy: $PORT (Railway exposed)
uvicorn main:app --host 127.0.0.1 --port 8001 &
streamlit run app_ui.py --server.port 8500 --server.address 127.0.0.1 &
sleep 8
exec python proxy.py 8001 8500
