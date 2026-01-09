#!/bin/bash
set -e

# Start nginx in background
nginx -g "daemon off;" &
NGINX_PID=$!

# Start backend
uvicorn main:app --host 0.0.0.0 --port 8080 &
UVICORN_PID=$!

# Wait for either process to exit
wait -n $NGINX_PID $UVICORN_PID

# If one exits, kill the other
kill $NGINX_PID $UVICORN_PID 2>/dev/null || true
