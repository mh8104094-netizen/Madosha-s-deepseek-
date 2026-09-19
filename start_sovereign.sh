#!/usr/bin/env bash
set -u

export OLLAMA_HOST="127.0.0.1:11435"
export OLLAMA_NUM_PARALLEL="1"
export OLLAMA_MAX_LOADED_MODELS="1"
export OLLAMA_CONTEXT_LENGTH="${XMIND_LOCAL_CONTEXT:-1536}"
export OLLAMA_KEEP_ALIVE="5m"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/tmp/xmind-ollama-models}"
mkdir -p "$OLLAMA_MODELS"

echo "[XMIND] starting sovereign app on port ${PORT:-80}"
python -m uvicorn sovereign:app --host 0.0.0.0 --port "${PORT:-80}" &
APP_PID=$!

echo "[XMIND] starting local cortex proxy on 127.0.0.1:11434"
python -m uvicorn cortex_proxy:app --host 127.0.0.1 --port 11434 &

(
  set +e
  echo "[CORTEX] bootstrap started; model=${XMIND_CORTEX_MODEL:-qwen3:0.6b}"
  echo "[CORTEX] RAM-safe context=${XMIND_LOCAL_CONTEXT:-1536}"

  if ! command -v curl >/dev/null 2>&1; then
    echo "[CORTEX][ERROR] curl is not installed in the Railway runtime"
    exit 0
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "[CORTEX] installing Ollama locally..."
    curl -fsSL https://ollama.com/install.sh | sh
    INSTALL_RC=$?
    echo "[CORTEX] Ollama installer exit code: $INSTALL_RC"
  else
    echo "[CORTEX] Ollama already present: $(command -v ollama)"
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "[CORTEX][ERROR] Ollama binary unavailable after install attempt"
    exit 0
  fi

  echo "[CORTEX] starting Ollama on 127.0.0.1:11435"
  OLLAMA_HOST=127.0.0.1:11435 ollama serve 2>&1 | sed -u 's/^/[OLLAMA] /' &

  READY=0
  for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:11435/api/tags >/dev/null 2>&1; then
      READY=1
      echo "[CORTEX] Ollama API online after ${i} checks"
      break
    fi
    sleep 2
  done

  if [ "$READY" != "1" ]; then
    echo "[CORTEX][ERROR] Ollama API did not become ready"
    exit 0
  fi

  echo "[CORTEX] pulling ${XMIND_CORTEX_MODEL:-qwen3:0.6b} (first boot only for this ephemeral container)..."
  OLLAMA_HOST=127.0.0.1:11435 ollama pull "${XMIND_CORTEX_MODEL:-qwen3:0.6b}"
  PULL_RC=$?
  echo "[CORTEX] model pull exit code: $PULL_RC"

  if [ "$PULL_RC" = "0" ]; then
    echo "[CORTEX] local Qwen cortex ready"
    curl -s http://127.0.0.1:11435/api/tags || true
  else
    echo "[CORTEX][ERROR] model pull failed"
  fi
) &

wait "$APP_PID"
