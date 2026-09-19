from __future__ import annotations

import json
import os
from collections import defaultdict

import httpx
from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="X-MIND Local Cortex Proxy", version="0.2")
TARGET = os.getenv("XMIND_LLAMA_INTERNAL_URL", "http://127.0.0.1:11435").rstrip("/")
MODEL_NAME = os.getenv("XMIND_CORTEX_MODEL", "qwen3-0.6b-local")
MAX_PREDICT = int(os.getenv("XMIND_LOCAL_MAX_PREDICT", "384"))


def normalize_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    last_call_ids: dict[str, list[str]] = defaultdict(list)
    seq = 0
    for raw in messages:
        msg = dict(raw)
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            calls = []
            for idx, call in enumerate(msg.get("tool_calls") or []):
                c = dict(call)
                fn = dict(c.get("function") or {})
                call_id = c.get("id") or f"call_{seq}_{idx}"
                c["id"] = call_id
                c["type"] = c.get("type") or "function"
                c["function"] = fn
                name = fn.get("name")
                if name:
                    last_call_ids[name].append(call_id)
                calls.append(c)
            msg["tool_calls"] = calls
            msg.pop("tool_name", None)
            out.append(msg)
            seq += 1
            continue
        if role == "tool":
            name = msg.get("tool_name") or msg.get("name") or "tool"
            ids = last_call_ids.get(name) or []
            call_id = msg.get("tool_call_id") or (ids.pop(0) if ids else f"call_tool_{seq}")
            out.append({
                "role": "tool",
                "name": name,
                "tool_call_id": call_id,
                "content": msg.get("content", ""),
            })
            seq += 1
            continue
        msg.pop("tool_name", None)
        out.append(msg)
    return out


async def request_json(method: str, path: str, payload=None, timeout=240):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(method, TARGET + path, json=payload)
            if r.status_code >= 400:
                raise HTTPException(r.status_code, detail=r.text[:1400])
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, detail=f"Local llama.cpp cortex warming/unavailable: {str(e)[:350]}")


@app.get("/api/tags")
async def tags():
    await request_json("GET", "/health", timeout=5)
    return {"models": [{"name": MODEL_NAME, "model": MODEL_NAME, "details": {"family": "qwen3", "runtime": "llama.cpp"}}]}


@app.post("/api/chat")
async def chat(req: Request):
    incoming = await req.json()
    options = incoming.get("options") or {}
    messages = normalize_messages(incoming.get("messages") or [])
    tools = incoming.get("tools") or []
    max_tokens = min(int(options.get("num_predict", MAX_PREDICT)), MAX_PREDICT)

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "temperature": float(options.get("temperature", 0.55)),
        "top_p": float(options.get("top_p", 0.9)),
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    data = await request_json("POST", "/v1/chat/completions", payload=payload, timeout=300)
    choices = data.get("choices") or []
    if not choices:
        raise HTTPException(502, detail="llama.cpp returned no completion choice")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []

    # Never surface hidden reasoning content to the app UI.
    result = {"role": "assistant", "content": content}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return {"message": result, "done": True, "model": MODEL_NAME}


@app.get("/health")
async def health():
    try:
        data = await request_json("GET", "/health", timeout=5)
        return {"ok": True, "target": TARGET, "model": MODEL_NAME, "runtime": "llama.cpp", "upstream": data}
    except HTTPException as e:
        return {"ok": False, "target": TARGET, "model": MODEL_NAME, "runtime": "llama.cpp", "detail": e.detail}
