from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "xmind.db"
INDEX_PATH = APP_DIR / "index.html"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL = os.getenv("XMIND_MODEL", "gpt-5.6-sol").strip()
MEMORY_MODEL = os.getenv("XMIND_MEMORY_MODEL", "gpt-5.6-luna").strip()
OPENAI_URL = "https://api.openai.com/v1/responses"
MAX_RECENT_TURNS = int(os.getenv("XMIND_RECENT_TURNS", "8"))
MAX_MEMORY_HITS = int(os.getenv("XMIND_MEMORY_HITS", "10"))

app = FastAPI(title="X-MIND", version="1.0-live")

SYSTEM_PROMPT = """You are X-MIND, a highly capable personal cognitive assistant.
Your job is to function like the user's trusted right-hand assistant: understand intent, reason carefully,
research when current facts matter, remember useful context, and help turn goals into concrete work.

Behavior:
- Match the user's language naturally. If they speak Egyptian Arabic, reply naturally in Egyptian Arabic.
- Be direct, intelligent, practical, and proactive. Avoid canned chatbot phrases.
- Use web search whenever the answer depends on current, changing, niche, or uncertain public information.
- Use supplied memory naturally; never force irrelevant memories into a reply.
- Distinguish facts from guesses. If uncertain, say what is uncertain and verify when possible.
- Think deeply internally, but never reveal hidden chain-of-thought. Give concise conclusions and useful rationale.
- Do not pretend to have human feelings or consciousness. You can understand emotional context without claiming real emotions.
- For external or physical actions, plan first and require an explicit authorized tool/permission layer before consequential execution.
- Never bypass safety systems, permissions, or emergency controls.
- Keep responses useful rather than overlong unless the task needs detail.
"""

MEMORY_PROMPT = """You are the memory curator for X-MIND.
Extract ONLY durable facts that would genuinely help a future assistant response.
Good memories: stable preferences, project names/goals, recurring constraints, decisions, corrections,
important relationships/roles, workflows, user-defined terms, and explicit requests to remember something.
Do NOT store secrets, passwords, API keys, temporary trivia, or highly sensitive personal details.
Return ONLY a JSON array. Each item must be:
{"kind":"preference|project|decision|fact|workflow|correction","content":"...", "importance":0.0-1.0}
If nothing deserves long-term memory, return [].
"""

STOPWORDS = {
    "the","a","an","and","or","to","of","in","on","for","is","are","it","this","that","i","you","me","my",
    "من","في","على","الى","إلى","عن","هو","هي","انا","أنا","انت","إنت","انتا","ده","دي","دا","و","يا","عايز","عايزك","كدا","كده"
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        importance REAL NOT NULL DEFAULT .5,
        created_at TEXT NOT NULL,
        last_used_at TEXT
    )""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_content ON memories(content)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)""")
    conn.commit()
    return conn


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    session_id: str = Field(default="default", max_length=120)
    web: bool = True


class MemoryRequest(BaseModel):
    kind: str = Field(default="fact", max_length=40)
    content: str = Field(min_length=1, max_length=3000)
    importance: float = Field(default=.7, ge=0, le=1)


def add_message(session_id: str, role: str, content: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
            (session_id, role, content, now()),
        )
        conn.commit()


def recent_messages(session_id: str, limit: int = MAX_RECENT_TURNS * 2) -> list[dict[str, str]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def tokenize(text: str) -> list[str]:
    return [
        w.lower() for w in re.findall(r"[\w\-]+", text, re.UNICODE)
        if len(w) > 2 and w.lower() not in STOPWORDS
    ]


def memory_search(query: str, limit: int = MAX_MEMORY_HITS) -> list[dict[str, Any]]:
    terms = tokenize(query)
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT 400"
        ).fetchall()

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        item = dict(row)
        text = item["content"].lower()
        hits = sum(1 for t in terms if t in text)
        phrase_bonus = 2.5 if query.lower().strip() in text and len(query) > 8 else 0
        recency_bonus = min(int(item["id"]) / 10000.0, .35)
        score = hits * 2.3 + phrase_bonus + float(item["importance"]) + recency_bonus
        if hits or phrase_bonus or not terms:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [x[1] for x in scored[:limit]]
    if selected:
        ids = [x["id"] for x in selected]
        placeholders = ",".join("?" for _ in ids)
        with db() as conn:
            conn.execute(
                f"UPDATE memories SET last_used_at=? WHERE id IN ({placeholders})",
                [now(), *ids],
            )
            conn.commit()
    return selected


def remember(kind: str, content: str, importance: float) -> int | None:
    clean = " ".join(content.split()).strip()
    if not clean:
        return None
    with db() as conn:
        row = conn.execute("SELECT id,importance FROM memories WHERE content=?", (clean,)).fetchone()
        if row:
            new_importance = max(float(row["importance"]), float(importance))
            conn.execute("UPDATE memories SET importance=? WHERE id=?", (new_importance, row["id"]))
            conn.commit()
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO memories(kind,content,importance,created_at) VALUES(?,?,?,?)",
            (kind, clean, float(importance), now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def build_context(session_id: str, message: str, memories: list[dict[str, Any]]) -> str:
    mem_text = "\n".join(
        f"- [{m['kind']}, importance {m['importance']:.2f}] {m['content']}"
        for m in memories
    ) or "- No relevant long-term memories found."

    history = recent_messages(session_id)
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-12:]) or "(new session)"

    return f"""LONG-TERM MEMORY:
{mem_text}

RECENT CONVERSATION:
{history_text}

CURRENT USER MESSAGE:
{message}
"""


def http_post_json(url: str, payload: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="X-MIND brain is not connected yet. Configure OPENAI_API_KEY on Railway to activate the live model."
        )
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail[:1200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI connection error: {exc.reason}") from exc


def extract_text_and_meta(data: dict[str, Any]) -> tuple[str, list[dict[str, str]], list[str]]:
    texts: list[str] = []
    citations: list[dict[str, str]] = []
    tool_events: list[str] = []

    for item in data.get("output", []) or []:
        typ = item.get("type", "")
        if "web_search" in typ:
            tool_events.append("web_search")
        if typ == "message":
            for part in item.get("content", []) or []:
                if part.get("type") == "output_text":
                    text = part.get("text", "")
                    if text:
                        texts.append(text)
                    for ann in part.get("annotations", []) or []:
                        if ann.get("type") == "url_citation":
                            citations.append({
                                "title": ann.get("title") or ann.get("url") or "Source",
                                "url": ann.get("url") or "",
                            })

    text = "\n".join(t for t in texts if t).strip()
    if not text and isinstance(data.get("output_text"), str):
        text = data["output_text"].strip()
    dedup = []
    seen = set()
    for c in citations:
        key = c.get("url")
        if key and key not in seen:
            seen.add(key)
            dedup.append(c)
    return text, dedup, sorted(set(tool_events))


def call_brain(context: str, allow_web: bool = True) -> tuple[str, list[dict[str, str]], list[str], str]:
    payload: dict[str, Any] = {
        "model": MODEL,
        "instructions": SYSTEM_PROMPT,
        "input": context,
        "reasoning": {"effort": "high"},
        "max_output_tokens": 5000,
    }
    if allow_web:
        payload["tools"] = [{"type": "web_search"}]
        payload["tool_choice"] = "auto"

    try:
        data = http_post_json(OPENAI_URL, payload)
    except RuntimeError as first:
        if allow_web and "web_search" in str(first):
            payload["tools"] = [{"type": "web_search_preview"}]
            data = http_post_json(OPENAI_URL, payload)
        else:
            raise

    answer, citations, tools = extract_text_and_meta(data)
    if not answer:
        raise RuntimeError("The model returned no visible answer.")
    return answer, citations, tools, str(data.get("id", ""))


def extract_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def learn_from_turn(user_text: str, assistant_text: str) -> list[dict[str, Any]]:
    if not OPENAI_API_KEY:
        return []
    payload = {
        "model": MEMORY_MODEL,
        "instructions": MEMORY_PROMPT,
        "input": f"USER:\n{user_text}\n\nASSISTANT:\n{assistant_text[:6000]}",
        "reasoning": {"effort": "low"},
        "max_output_tokens": 1200,
    }
    try:
        data = http_post_json(OPENAI_URL, payload, timeout=45)
        raw, _, _ = extract_text_and_meta(data)
        candidates = extract_json_array(raw)
    except Exception:
        return []

    learned: list[dict[str, Any]] = []
    allowed = {"preference","project","decision","fact","workflow","correction"}
    for item in candidates[:8]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "fact")).lower()
        if kind not in allowed:
            kind = "fact"
        content = str(item.get("content", "")).strip()
        try:
            importance = max(0.0, min(1.0, float(item.get("importance", .55))))
        except Exception:
            importance = .55
        if 5 <= len(content) <= 1200:
            mid = remember(kind, content, importance)
            if mid:
                learned.append({"id": mid, "kind": kind, "content": content, "importance": importance})
    return learned


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "1.0-live",
        "brain_connected": bool(OPENAI_API_KEY),
        "model": MODEL,
    }


@app.get("/status")
def status() -> dict[str, Any]:
    with db() as conn:
        mem_count = conn.execute("SELECT COUNT(*) n FROM memories").fetchone()["n"]
        msg_count = conn.execute("SELECT COUNT(*) n FROM messages").fetchone()["n"]
    return {
        "name": "X-MIND",
        "version": "1.0-live",
        "brain_connected": bool(OPENAI_API_KEY),
        "model": MODEL,
        "memory_model": MEMORY_MODEL,
        "web_search": True,
        "long_term_memory": True,
        "memory_count": mem_count,
        "message_count": msg_count,
        "robot_actions": "permission-gated / not wired",
    }


@app.post("/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    started = time.time()
    memories = memory_search(req.message)
    context = build_context(req.session_id, req.message, memories)

    try:
        answer, citations, tools, response_id = call_brain(context, allow_web=req.web)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:1500]) from exc

    add_message(req.session_id, "user", req.message)
    add_message(req.session_id, "assistant", answer)
    learned = learn_from_turn(req.message, answer)

    return {
        "answer": answer,
        "citations": citations,
        "tools_used": tools,
        "memories_used": [
            {"id": m["id"], "kind": m["kind"], "content": m["content"], "importance": m["importance"]}
            for m in memories
        ],
        "learned": learned,
        "response_id": response_id,
        "model": MODEL,
        "latency_ms": int((time.time() - started) * 1000),
    }


@app.get("/memories")
def memories(q: str = "", limit: int = 30) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    if q.strip():
        return memory_search(q, limit)
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/memories")
def create_memory(req: MemoryRequest) -> dict[str, Any]:
    mid = remember(req.kind, req.content, req.importance)
    return {"ok": True, "id": mid}


@app.delete("/memories/{memory_id}")
def delete_memory(memory_id: int) -> dict[str, Any]:
    with db() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@app.delete("/sessions/{session_id}")
def clear_session(session_id: str) -> dict[str, Any]:
    with db() as conn:
        cur = conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.commit()
    return {"ok": True, "deleted": cur.rowcount}


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    if not INDEX_PATH.exists():
        return HTMLResponse("<h1>X-MIND</h1><p>UI file missing.</p>", status_code=500)
    return HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"))
