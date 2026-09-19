from __future__ import annotations

import json
import time
import urllib.request
import uuid

BASE = "http://127.0.0.1:80"


def post_chat(message: str, session_id: str | None = None):
    body = {"message": message, "session_id": session_id}
    req = urllib.request.Request(
        BASE + "/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


session = "__probe_" + uuid.uuid4().hex
for i in range(60):
    try:
        a = post_chat("hello", session)
        print("[CONVO-PROBE] HELLO:", (a.get("answer") or "")[:300], flush=True)
        b = post_chat("ازيك؟", a.get("session_id"))
        print("[CONVO-PROBE] ARABIC:", (b.get("answer") or "")[:300], flush=True)
        if a.get("answer") and b.get("answer"):
            print("[CONVO-PROBE] CONVERSATION_OK", flush=True)
        break
    except Exception as e:
        if i % 5 == 0:
            print(f"[CONVO-PROBE] warming ({i+1}/60): {type(e).__name__}", flush=True)
        time.sleep(2)
