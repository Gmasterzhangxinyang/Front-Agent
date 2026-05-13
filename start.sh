#!/bin/bash
# Railway sets $PORT to the exposed port
# proxy listens on $PORT (foreground)
# uvicorn on 8080 (internal), streamlit on 8500 (internal)

uvicorn main:app --host 127.0.0.1 --port 8080 &
streamlit run app_ui.py --server.port 8500 --server.address 127.0.0.1 &

sleep 8

# proxy binds to $PORT (Railway's exposed port), routes to internal ports
exec python proxy.py 8080 8500
