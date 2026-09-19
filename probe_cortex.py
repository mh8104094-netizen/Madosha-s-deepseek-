from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11434"


def log(msg: str) -> None:
    print(f"[CORTEX-PROBE] {msg}", flush=True)


def get_json(url: str, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(url: str, payload: dict, timeout=90):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    for i in range(90):
        try:
            tags = get_json(BASE + "/api/tags")
            log(f"cortex online: {tags}")
            break
        except Exception:
            if i in {0, 9, 29, 59}:
                log(f"warming up ({i + 1}/90)")
            time.sleep(2)
    else:
        log("FAILED: cortex did not become ready")
        return

    try:
        out = post_json(
            BASE + "/api/chat",
            {
                "model": "qwen3-0.6b-local",
                "messages": [{"role": "user", "content": "Reply exactly: X-MIND LOCAL ONLINE"}],
                "stream": False,
                "options": {"num_predict": 24, "temperature": 0.1, "top_p": 0.9},
            },
        )
        text = ((out.get("message") or {}).get("content") or "").strip()
        log(f"INFERENCE_OK: {text[:160]}")
    except Exception as e:
        log(f"INFERENCE_FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
