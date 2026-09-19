from __future__ import annotations

import os
import httpx
from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="X-MIND Local Cortex Proxy", version="0.1")
TARGET = os.getenv("XMIND_OLLAMA_INTERNAL_URL", "http://127.0.0.1:11435").rstrip("/")
MAX_CTX = int(os.getenv("XMIND_LOCAL_CONTEXT", "1536"))
MAX_PREDICT = int(os.getenv("XMIND_LOCAL_MAX_PREDICT", "512"))


async def forward(method: str, path: str, payload=None):
    try:
        async with httpx.AsyncClient(timeout=240) as client:
            r = await client.request(method, TARGET + path, json=payload)
            if r.status_code >= 400:
                raise HTTPException(r.status_code, detail=r.text[:1000])
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, detail=f"Local cortex warming/unavailable: {str(e)[:300]}")


@app.get("/api/tags")
async def tags():
    return await forward("GET", "/api/tags")


@app.post("/api/chat")
async def chat(req: Request):
    payload = await req.json()
    options = payload.setdefault("options", {})
    try:
        requested_ctx = int(options.get("num_ctx", MAX_CTX))
    except Exception:
        requested_ctx = MAX_CTX
    options["num_ctx"] = min(requested_ctx, MAX_CTX)
    options["num_predict"] = min(int(options.get("num_predict", MAX_PREDICT)), MAX_PREDICT)
    payload["stream"] = False
    payload["think"] = False
    return await forward("POST", "/api/chat", payload)


@app.get("/health")
async def health():
    try:
        data = await forward("GET", "/api/tags")
        return {"ok": True, "target": TARGET, "max_ctx": MAX_CTX, "models": [m.get("name") for m in data.get("models", [])]}
    except HTTPException as e:
        return {"ok": False, "target": TARGET, "max_ctx": MAX_CTX, "detail": e.detail}
