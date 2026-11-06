#!/usr/bin/env bash
# ==============================================================================
# YANTRIK DWS-S01 Desktop One-Click Launcher
# Automatically launches the embedded edge server and opens the operator HMI.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=8000
echo "======================================================================"
echo "          STARTING YANTRIK DWS-S01 STATIC WORKSTATION                 "
echo "======================================================================"

# Check if port 8000 is already running
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "[YANTRIK] Port $PORT is already active. Opening browser..."
else
    echo "[YANTRIK] Starting background edge server on port $PORT..."
    python3 src/yantrik_dws/server.py &
    SERVER_PID=$!
    echo "[YANTRIK] Server PID: $SERVER_PID"
    sleep 1
fi

echo "[YANTRIK] Opening Operator Touchscreen HMI..."
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:$PORT/" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
    open "http://localhost:$PORT/" >/dev/null 2>&1 || true
fi

echo "======================================================================"
echo "  YANTRIK DWS-S01 Active: http://localhost:$PORT/"
echo "======================================================================"
