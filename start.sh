#!/bin/bash
# uvicorn on internal 8000, streamlit directly on $PORT (no proxy)
uvicorn main:app --host 127.0.0.1 --port 8000 &
streamlit run app_ui.py --server.port ${PORT:-8080} --server.address 0.0.0.0 &
wait
