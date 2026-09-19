from __future__ import annotations

import re, uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

import sovereign_v2 as core

app = FastAPI(title="X-MIND Natural Conversation Core", version="0.5.0")

GENERIC_PATTERNS = [
    "how can i assist you",
    "how can i help you",
    "how may i assist you",
    "what can i help you with",
    "what can i do for you",
    "كيف يمكنني مساعدتك",
    "كيف أقدر أساعدك",
    "ازاي اقدر اساعدك",
    "إزاي أقدر أساعدك",
]


def has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def language_name(text: str) -> str:
    return "Egyptian Arabic" if has_arabic(text) else "the user's language"


def bad_generic(answer: str, user_text: str) -> bool:
    a = (answer or "").strip().lower()
    if not a:
        return True
    if any(p in a for p in GENERIC_PATTERNS):
        return True
    if has_arabic(user_text) and not has_arabic(answer):
        return True
    # very short greetings should not trigger a long support-style paragraph
    if core.is_greeting_or_smalltalk(user_text) and len(answer) > 260:
        return True
    # catch obvious sentence duplication
    parts = [re.sub(r"\s+", " ", x).strip().lower() for x in re.split(r"[.!؟!?]+", answer) if x.strip()]
    if len(parts) >= 2 and len(set(parts)) < len(parts):
        return True
    return False


def filtered_history(session: str, user_text: str):
    recent = core.history(session, 4)
    if core.is_greeting_or_smalltalk(user_text):
        recent = recent[-2:]
    if has_arabic(user_text):
        # Do not let a previous English assistant greeting drag an Arabic turn back into English.
        recent = [m for m in recent if m["role"] == "user" or has_arabic(m["content"])]
    return recent[-4:]


def conversation_system(user_text: str, casual: bool) -> str:
    if has_arabic(user_text):
        return """أنت X-MIND، المساعد الشخصي وذراع المستخدم اليمين. رد بالمصري الطبيعي فقط في هذه الرسالة.
قواعد صارمة:
- جاوب الرسالة الحالية مباشرة، مش كأنك موظف خدمة عملاء.
- ممنوع تستخدم إنجليزي إلا لو المستخدم طلبه.
- ممنوع تقول: كيف أساعدك، إزاي أقدر أساعدك، تحت أمرك، أو أي جملة دعم محفوظة إلا لو السياق محتاجها فعلاً.
- لو المستخدم بيقول تحية أو بيسأل عليك، رد طبيعي قصير كصاحب ذكي، من غير ما تعيد التحية مرتين ومن غير ما تعرّف نفسك.
- ما تكررش نفس الجملة أو نفس المعنى بصيغتين.
- حافظ على شخصية X-MIND: ذكي، هادي، مباشر، فاهم السياق.
- لا تعرض سلسلة التفكير الداخلية."""
    return """You are X-MIND, the user's personal right-hand AI.
For this turn, talk naturally like a smart familiar assistant, not customer support.
Answer the current message directly. Do not say 'How can I help/assist you today?', do not reintroduce yourself, and do not repeat the greeting or the same idea twice. Keep casual replies short. Do not expose hidden chain-of-thought."""


async def generate_with_gate(user_text: str, session: str, memory_block: str = "", research_block: str = ""):
    casual = core.is_greeting_or_smalltalk(user_text)
    system = conversation_system(user_text, casual)
    extras = []
    if memory_block:
        extras.append("Relevant memory:\n" + memory_block)
    if research_block:
        extras.append("Fresh research:\n" + research_block)
    if extras:
        system += "\n\n" + "\n\n".join(extras)

    recent = filtered_history(session, user_text)
    msgs = [{"role": "system", "content": system}, *recent, {"role": "user", "content": user_text}]
    first = await core.cortex(msgs, max_tokens=80 if casual else 260, temperature=.82 if casual else .64)
    answer = core.clean_text(first.get("content") or "", 4000)
    regenerated = False

    if bad_generic(answer, user_text):
        regenerated = True
        correction = conversation_system(user_text, casual) + "\n\nThe previous draft was rejected because it was generic, repetitive, or used the wrong language. Produce a fresh response now. Do not mention the rejected draft."
        if has_arabic(user_text):
            correction += "\nالرد لازم يكون بالمصري فقط، طبيعي ومختلف، ومن غير أي جملة من نوع إزاي أقدر أساعدك."
        retry_msgs = [{"role": "system", "content": correction}, {"role": "user", "content": user_text}]
        second = await core.cortex(retry_msgs, max_tokens=72 if casual else 220, temperature=.9 if casual else .7)
        second_answer = core.clean_text(second.get("content") or "", 4000)
        if second_answer:
            answer = second_answer

    return answer, regenerated


@app.get("/health")
async def health():
    online, _ = await core.cortex_online()
    return {"ok": True, "version": "0.5.0", "cortex_connected": online, "model": core.CORTEX_MODEL}


@app.get("/status")
async def status():
    online, error = await core.cortex_online()
    return {
        "name": "X-MIND",
        "version": "0.5.0-natural",
        "cortex": {"connected": online, "model": core.CORTEX_MODEL, "error": error},
        "research": {"enabled": core.SEARCH_ENABLED, "provider": "direct-web"},
        "memory": {"path": str(core.DB_PATH), "persistent": str(core.DATA_DIR).startswith("/data")},
        "quality_gate": True,
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
    memory_block = "\n".join(f"- {core.clean_text(m['content'], 200)}" for m in memories_used)

    sources = []
    research_block = ""
    if do_research:
        try:
            results = await core.web_search(user_text, 4)
            if results:
                sources = [x["url"] for x in results if x.get("url")]
                research_block = "\n".join(f"- {x['title']}: {x['snippet']} ({x['url']})" for x in results)
        except Exception:
            pass

    answer, regenerated = await generate_with_gate(user_text, session, memory_block, research_block)
    if not answer:
        answer = "أنا معاك." if has_arabic(user_text) else "I'm with you."

    core.add_message(session, "user", user_text)
    core.add_message(session, "assistant", answer)

    return {
        "session_id": session,
        "answer": answer,
        "model": core.CORTEX_MODEL,
        "mode": "conversation" if casual else ("research" if do_research else "assistant"),
        "quality_regenerated": regenerated,
        "memory_used": memories_used,
        "memory_stored": stored_id,
        "sources": list(dict.fromkeys(sources))[:8],
    }


HTML = core.HTML.replace("CONVERSATION CORE ·", "NATURAL CORE v0.5 ·").replace("xmind_session_v4", "xmind_session_v5")


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
