from __future__ import annotations

import re
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

import sovereign_v2 as core

app = FastAPI(title="X-MIND Natural Core", version="0.6.1")

GENERIC = [
    "how can i help", "how can i assist", "how may i assist", "what can i help",
    "what can i do for you", "customer service", "خدمة العملاء", "أنا هنا للمساعدة",
    "هنا لمساعدتك", "لمساعدتك", "كيف يمكنني مساعد", "كيف أقدر أساعد",
    "ازاي اقدر اساعد", "إزاي أقدر أساعد", "هل هناك شيء محدد", "ترغب في استفسار",
    "يمكنني مساعد",
]


def has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def wordset(text: str) -> set[str]:
    return {w for w in re.findall(r"[\w\u0600-\u06ff]+", normalize(text), re.UNICODE) if len(w) > 1}


def similarity(a: str, b: str) -> float:
    aa, bb = wordset(a), wordset(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def social_checkin(text: str) -> bool:
    t = normalize(text)
    arabic = ["ازيك", "إزيك", "عامل ايه", "عامل إيه", "اخبارك", "أخبارك", "الدنيا معاك", "طمني عليك"]
    english = ["how are you", "how's it going", "hows it going", "you good"]
    return any(x.lower() in t for x in arabic + english)


def recent_assistant(session: str, limit: int = 3) -> list[str]:
    with core.db() as c:
        rows = c.execute(
            "SELECT content FROM messages WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT ?",
            (session, limit),
        ).fetchall()
    return [r["content"] for r in rows]


def generic(text: str) -> bool:
    t = normalize(text)
    return any(x.lower() in t for x in GENERIC)


def sanitize(text: str, user_text: str) -> str:
    text = core.clean_text(text, 4000)
    if not text:
        return ""
    chunks = [x.strip() for x in re.split(r"(?<=[.!?؟])\s+|\n+", text) if x.strip()]
    kept = [x for x in chunks if not generic(x)]
    if chunks and not kept:
        return ""
    if kept:
        text = " ".join(kept).strip()
    if has_arabic(user_text) and not has_arabic(text):
        return ""
    return text


def bad(text: str, user_text: str, prior: list[str]) -> bool:
    if not text or generic(text):
        return True
    if has_arabic(user_text) and not has_arabic(text):
        return True
    if core.is_greeting_or_smalltalk(user_text) and len(text) > 220:
        return True
    if any(similarity(text, p) >= .62 for p in prior if p):
        return True
    sentences = [normalize(x) for x in re.split(r"[.!?؟]+", text) if normalize(x)]
    return len(sentences) >= 2 and len(set(sentences)) < len(sentences)


def system_prompt(user_text: str, casual: bool, retry: int = 0) -> str:
    checkin = social_checkin(user_text)
    if has_arabic(user_text):
        base = "أنت X-MIND، رفيق ذكي ومساعد شخصي قريب من المستخدم. اتكلم بالمصري الطبيعي وجاوب معنى آخر رسالة مباشرة."
        if checkin:
            base += " المستخدم بيسأل عليك أنت؛ رد على حالك بشكل طبيعي وودود، وممكن تسأله هو أخباره إيه."
        elif casual:
            base += " في الكلام الاجتماعي خليك بسيط وخفيف في جملة أو جملتين."
        else:
            base += " في الأسئلة الفعلية جاوب بوضوح وبشكل عملي."
        base += " ما تعرّفش نفسك من غير سبب وما تسردش قدراتك."
        if retry:
            base += " جرّب صياغة مختلفة وأقصر وأكثر تلقائية."
        return base
    base = "You are X-MIND, a smart familiar personal companion and assistant. Reply directly to the meaning of the latest message."
    if checkin:
        base += " The user is asking how you are; answer that social check-in naturally and you may ask how they are too."
    elif casual:
        base += " Keep social conversation simple and warm in one or two sentences."
    else:
        base += " Answer real questions clearly and practically."
    base += " Do not introduce yourself or list capabilities without a reason."
    if retry:
        base += " Use a different, shorter, more spontaneous wording."
    return base


def compact_history(session: str, user_text: str) -> list[dict]:
    recent = core.history(session, 4)
    if core.is_greeting_or_smalltalk(user_text):
        recent = recent[-2:]
    if has_arabic(user_text):
        recent = [m for m in recent if m["role"] == "user" or has_arabic(m["content"])]
    return recent[-3:]


async def generate(user_text: str, session: str, memory_block: str = "", research_block: str = ""):
    casual = core.is_greeting_or_smalltalk(user_text)
    prior = recent_assistant(session, 3)
    candidates: list[str] = []

    for attempt in range(3):
        system = system_prompt(user_text, casual, attempt)
        if attempt == 0:
            extras = []
            if memory_block:
                extras.append("Relevant memory:\n" + memory_block)
            if research_block:
                extras.append("Fresh research:\n" + research_block)
            if extras:
                system += "\n\n" + "\n\n".join(extras)
            history = compact_history(session, user_text)
        elif attempt == 1:
            history = compact_history(session, user_text)[-1:]
        else:
            history = []

        msgs = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_text}]
        m = await core.cortex(msgs, max_tokens=56 if casual else 190, temperature=.88 if casual else .66)
        cleaned = sanitize(core.clean_text(m.get("content") or "", 4000), user_text)
        if cleaned:
            candidates.append(cleaned)
        if cleaned and not bad(cleaned, user_text, prior):
            return cleaned, attempt

    if candidates:
        ranked = sorted(candidates, key=lambda x: (generic(x), max([similarity(x, p) for p in prior] or [0]), len(x)))
        return ranked[0], 2
    return ("موجود معاك." if has_arabic(user_text) else "I'm here."), 2


@app.get("/health")
async def health():
    online, _ = await core.cortex_online()
    return {"ok": True, "version": "0.6.1", "cortex_connected": online, "model": core.CORTEX_MODEL}


@app.get("/status")
async def status():
    online, error = await core.cortex_online()
    return {
        "name": "X-MIND",
        "version": "0.6.1-natural",
        "cortex": {"connected": online, "model": core.CORTEX_MODEL, "error": error},
        "research": {"enabled": core.SEARCH_ENABLED, "provider": "direct-web"},
        "memory": {"path": str(core.DB_PATH), "persistent": str(core.DATA_DIR).startswith("/data")},
        "quality_gate": {"enabled": True, "anti_repetition": True, "social_intent": True, "max_attempts": 3},
        "external_ai_api_required": False,
    }


@app.get("/memories")
def memories(limit: int = 18):
    with core.db() as c:
        rows = c.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 50),)).fetchall()
    return [dict(r) for r in rows]


@app.post("/chat")
async def chat(req: core.ChatRequest):
    session = req.session_id or uuid.uuid4().hex
    online, error = await core.cortex_online()
    if not online:
        raise HTTPException(503, detail={"message": "Local X-MIND cortex is warming up or unavailable.", "error": error})

    user_text = req.message.strip()
    stored_id = None
    explicit = core.explicit_memory(user_text)
    if explicit:
        stored_id = core.remember(explicit, "preference", .84)

    casual = core.is_greeting_or_smalltalk(user_text) and not req.force_research
    do_research = core.needs_research(user_text, req.force_research) and not casual
    memories_used = [] if casual else core.recall(user_text, 3)
    memory_block = "\n".join(f"- {core.clean_text(m['content'], 180)}" for m in memories_used)

    sources: list[str] = []
    research_block = ""
    if do_research:
        try:
            results = await core.web_search(user_text, 4)
            sources = [x["url"] for x in results if x.get("url")]
            research_block = "\n".join(f"- {x['title']}: {x['snippet']} ({x['url']})" for x in results)
        except Exception:
            pass

    answer, attempts = await generate(user_text, session, memory_block, research_block)
    core.add_message(session, "user", user_text)
    core.add_message(session, "assistant", answer)
    return {
        "session_id": session,
        "answer": answer,
        "model": core.CORTEX_MODEL,
        "mode": "conversation" if casual else ("research" if do_research else "assistant"),
        "quality_attempt": attempts + 1,
        "memory_used": memories_used,
        "memory_stored": stored_id,
        "sources": list(dict.fromkeys(sources))[:8],
    }


HTML = core.HTML.replace("CONVERSATION CORE ·", "NATURAL CORE v0.6 ·").replace("xmind_session_v4", "xmind_session_v61")


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
