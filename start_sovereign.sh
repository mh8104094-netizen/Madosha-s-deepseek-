#!/usr/bin/env bash
set -u

echo "[XMIND] starting sovereign app on port ${PORT:-80}"
python -m uvicorn sovereign:app --host 0.0.0.0 --port "${PORT:-80}" &
APP_PID=$!

echo "[XMIND] starting cortex compatibility proxy on 127.0.0.1:11434"
python -m uvicorn cortex_proxy:app --host 127.0.0.1 --port 11434 &
PROXY_PID=$!

echo "[CORTEX] starting lightweight llama.cpp bootstrap in background"
python bootstrap_llama.py &
LLAMA_PID=$!

cleanup() {
  kill "$PROXY_PID" "$LLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait "$APP_PID"
