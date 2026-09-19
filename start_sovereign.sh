#!/usr/bin/env bash
set -u

echo "[XMIND] starting natural conversation core v0.6 on port ${PORT:-80}"
python -m uvicorn sovereign_v4:app --host 0.0.0.0 --port "${PORT:-80}" &
APP_PID=$!

echo "[XMIND] starting cortex compatibility proxy on 127.0.0.1:11434"
python -m uvicorn cortex_proxy:app --host 127.0.0.1 --port 11434 &
PROXY_PID=$!

echo "[CORTEX] starting lightweight llama.cpp bootstrap in background"
python bootstrap_llama.py &
LLAMA_PID=$!

echo "[CORTEX] starting inference self-test in background"
python probe_cortex.py &
PROBE_PID=$!

echo "[XMIND] starting isolated conversation self-test in background"
python probe_conversation.py &
CONVO_PROBE_PID=$!

cleanup() {
  kill "$PROXY_PID" "$LLAMA_PID" "$PROBE_PID" "$CONVO_PROBE_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait "$APP_PID"
