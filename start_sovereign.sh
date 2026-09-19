#!/usr/bin/env bash
set -u

export OLLAMA_HOST="127.0.0.1:11435"
export OLLAMA_NUM_PARALLEL="1"
export OLLAMA_MAX_LOADED_MODELS="1"
export OLLAMA_CONTEXT_LENGTH="${XMIND_LOCAL_CONTEXT:-1536}"
export OLLAMA_KEEP_ALIVE="5m"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/tmp/xmind-ollama-models}"
mkdir -p "$OLLAMA_MODELS" /tmp/xmind

# Start X-MIND immediately so Railway healthchecks pass while the local cortex warms up.
python -m uvicorn sovereign:app --host 0.0.0.0 --port "${PORT:-80}" >/tmp/xmind/app.log 2>&1 &
APP_PID=$!
python -m uvicorn cortex_proxy:app --host 127.0.0.1 --port 11434 >/tmp/xmind/proxy.log 2>&1 &

(
  set +e
  if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh >/tmp/xmind/ollama-install.log 2>&1
  fi
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA_HOST=127.0.0.1:11435 ollama serve >/tmp/xmind/ollama.log 2>&1 &
    for i in $(seq 1 60); do
      if curl -sf http://127.0.0.1:11435/api/tags >/dev/null 2>&1; then break; fi
      sleep 2
    done
    OLLAMA_HOST=127.0.0.1:11435 ollama pull "${XMIND_CORTEX_MODEL:-qwen3:0.6b}" >>/tmp/xmind/ollama-pull.log 2>&1
  fi
) &

wait "$APP_PID"
