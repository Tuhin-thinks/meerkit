#!/bin/bash

# Function to clean up background processes on exit
cleanup() {
    echo ""
    echo "Shutting down Meerkit backend and frontend..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "Starting Meerkit backend on port 5000..."
uv run flask --app meerkit.app run --debug --port 5000 &
BACKEND_PID=$!

echo "Starting Meerkit frontend..."
# Run npm run dev in the frontend directory
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Wait for background processes
wait "$BACKEND_PID" "$FRONTEND_PID"
