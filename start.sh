#!/bin/bash
# Start both FastAPI (uvicorn) and Streamlit in the same container

# Start uvicorn in background
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} &
UVICORN_PID=$!

# Start streamlit in background
streamlit run app_ui.py --server.port 8501 --server.address 0.0.0.0 &
STREAMLIT_PID=$!

# Wait for both to finish (if either dies, exit)
wait $UVICORN_PID $STREAMLIT_PID
