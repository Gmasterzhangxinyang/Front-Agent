#!/bin/bash
# uvicorn: 8000, streamlit: 8500, proxy: $PORT (Railway exposed)
uvicorn main:app --host 0.0.0.0 --port 8000 &
streamlit run app_ui.py --server.port 8500 --server.address 0.0.0.0 &
sleep 3
exec python proxy.py 8000 8500 $PORT
