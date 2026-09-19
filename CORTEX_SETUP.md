# X-MIND Sovereign Cortex

X-MIND no longer requires a third-party AI API. The default cortex is Qwen3-30B-A3B running on infrastructure you control.

## Recommended cortex

- Model: `qwen3:30b-a3b`
- Runtime: Ollama
- License: Apache-2.0

## Cortex node

Install Ollama on the GPU/local machine, then run:

```bash
ollama pull qwen3:30b-a3b
ollama serve
```

Configure the X-MIND orchestrator:

```env
XMIND_CORTEX_URL=http://YOUR-CORTEX-NODE:11434
XMIND_CORTEX_MODEL=qwen3:30b-a3b
XMIND_SEARCH_ENABLED=true
```

If X-MIND and Ollama run on the same machine, use `http://127.0.0.1:11434`.

## Architecture

Qwen is only the replaceable cortex. X-MIND keeps its own long-term memory, session history, direct-web research tools, identity, and safety boundary outside the model. This lets the cortex be replaced or fine-tuned later without losing the assistant's accumulated memory.
