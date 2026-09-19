from __future__ import annotations

import json, os, re, sqlite3, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("XMIND_DATA_DIR", str(APP_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "xmind.db"
CORTEX_URL = os.getenv("XMIND_CORTEX_URL", "http://127.0.0.1:11434").rstrip("/")
CORTEX_MODEL = os.getenv("XMIND_CORTEX_MODEL", "qwen3-0.6b-local")
SEARCH_ENABLED = os.getenv("XMIND_SEARCH_ENABLED", "true").lower() == "true"
UA = "Mozilla/5.0 X-MIND Sovereign Research Agent"

app = FastAPI(title="X-MIND Conversational Core", version="0.4.0")


def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, content TEXT NOT NULL, importance REAL NOT NULL DEFAULT .5, created_at TEXT NOT NULL, use_count INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS research_cache(key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL)")
    c.commit()
    return c


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    session_id: str | None = None
    force_research: bool = False


def tokenize(s: str) -> set[str]:
    return {x.lower() for x in re.findall(r"[\w\-]+", s, re.UNICODE) if len(x) >= 2}


def clean_text(s: str, limit: int = 420) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:limit]


def remember(content: str, kind: str = "semantic", importance: float = .72):
    content = clean_text(content, 700)
    if not content:
        return None
    with db() as c:
        old = c.execute("SELECT id FROM memories WHERE lower(content)=lower(?) LIMIT 1", (content,)).fetchone()
        if old:
            c.execute("UPDATE memories SET importance=max(importance,?), use_count=use_count+1 WHERE id=?", (importance, old["id"]))
            c.commit()
            return int(old["id"])
        cur = c.execute("INSERT INTO memories(kind,content,importance,created_at,use_count) VALUES(?,?,?,?,0)", (kind, content, importance, now()))
        c.commit()
        return int(cur.lastrowid)


def recall(query: str, limit: int = 3):
    q = tokenize(query)
    if not q:
        return []
    with db() as c:
        rows = c.execute("SELECT * FROM memories ORDER BY importance DESC,id DESC LIMIT 250").fetchall()
    scored = []
    for r in rows:
        d = dict(r)
        overlap = len(q & tokenize(d["content"]))
        phrase = 1.5 if query.lower() in d["content"].lower() else 0
        score = overlap * 2 + phrase + float(d["importance"])
        if overlap or phrase:
            scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:limit]]


def add_message(session_id: str, role: str, content: str):
    content = clean_text(content, 5000)
    if not content:
        return
    with db() as c:
        c.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)", (session_id, role, content, now()))
        c.commit()


def history(session_id: str, limit: int = 6):
    with db() as c:
        rows = c.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
    raw = [dict(r) for r in reversed(rows)]
    out = []
    prev = None
    for m in raw:
        text = clean_text(m["content"], 900)
        fingerprint = (m["role"], text.lower())
        if fingerprint == prev:
            continue
        out.append({"role": m["role"], "content": text})
        prev = fingerprint
    return out[-limit:]


def unwrap(href: str):
    try:
        q = parse_qs(urlparse(href).query)
        return unquote(q["uddg"][0]) if "uddg" in q else href
    except Exception:
        return href


async def web_search(query: str, max_results: int = 4):
    if not SEARCH_ENABLED:
        return []
    key = f"s:{query.lower()}:{max_results}"
    with db() as c:
        cached = c.execute("SELECT payload,created_at FROM research_cache WHERE key=?", (key,)).fetchone()
    if cached and time.time() - cached["created_at"] < 900:
        return json.loads(cached["payload"])
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=18, follow_redirects=True) as client:
        r = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for result in soup.select(".result"):
        a = result.select_one("a.result__a")
        if not a:
            continue
        sn = result.select_one(".result__snippet")
        out.append({
            "title": clean_text(a.get_text(" ", strip=True), 180),
            "url": unwrap(a.get("href", "")),
            "snippet": clean_text(sn.get_text(" ", strip=True) if sn else "", 320),
        })
        if len(out) >= max_results:
            break
    with db() as c:
        c.execute("INSERT OR REPLACE INTO research_cache(key,payload,created_at) VALUES(?,?,?)", (key, json.dumps(out, ensure_ascii=False), time.time()))
        c.commit()
    return out


def is_greeting_or_smalltalk(text: str) -> bool:
    t = text.strip().lower()
    words = tokenize(t)
    greetings = {"hello", "hi", "hey", "yo", "هلا", "اهلا", "أهلا", "هاي", "ازيك", "إزيك", "عامل", "اخبارك", "أخبارك", "صباح", "مساء"}
    if len(t) <= 32 and words & greetings:
        return True
    return len(t) <= 14 and len(words) <= 3


def needs_research(text: str, force: bool = False) -> bool:
    if force:
        return True
    t = text.lower()
    markers = ["ابحث", "دور على", "search", "latest", "current", "today", "دلوقتي", "اخر ", "آخر ", "أحدث", "خبر", "اخبار", "أخبار", "سعر", "موعد", "release", "2026"]
    return any(x in t for x in markers)


def explicit_memory(text: str):
    patterns = [
        r"^\s*(?:افتكر|إفتكر|remember)\s+(?:ان|إن|that)?\s*(.+)$",
        r"^\s*(?:خلي بالك|خلى بالك)\s+(?:ان|إن)?\s*(.+)$",
    ]
    for p in patterns:
        m = re.match(p, text, flags=re.I)
        if m and len(m.group(1).strip()) >= 3:
            return m.group(1).strip()
    return None


CASUAL_SYSTEM = """You are X-MIND, the user's personal right-hand AI. This is normal conversation, not a customer-support script.
Rules:
- Answer the user's CURRENT message first.
- Speak naturally in the same language and dialect the user uses; if Arabic is Egyptian, reply naturally in Egyptian Arabic.
- For greetings and casual talk, be brief and human-like: usually 1-3 sentences.
- Never repeat the greeting, your introduction, or the same sentence twice.
- Do not list your capabilities unless asked.
- Do not say generic phrases like 'How can I assist you today?' unless it genuinely fits.
- Keep continuity with only the recent conversation supplied below.
- You are X-MIND; Qwen is only your local cortex.
- Do not expose hidden chain-of-thought."""

AGENT_SYSTEM = """You are X-MIND, the user's personal right-hand AI. Be practical, direct, proactive, and natural.
Answer the current request, using supplied memory and research only when relevant. Do not repeat yourself or reintroduce yourself. Speak in the user's language and dialect. If evidence is provided from web research, distinguish what is known from what is uncertain and cite source URLs briefly. Never claim you performed an action that was not actually performed. Do not expose hidden chain-of-thought."""


async def cortex_online():
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            r = await client.get(CORTEX_URL + "/api/tags")
            r.raise_for_status()
        return True, None
    except Exception as e:
        return False, str(e)[:220]


async def cortex(messages, max_tokens=180, temperature=.72):
    payload = {
        "model": CORTEX_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": .9,
            "num_predict": max_tokens,
            "repeat_penalty": 1.18,
            "frequency_penalty": .18,
            "presence_penalty": .08,
        },
    }
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(CORTEX_URL + "/api/chat", json=payload)
        r.raise_for_status()
        return r.json().get("message", {})


@app.get("/health")
async def health():
    online, _ = await cortex_online()
    return {"ok": True, "version": "0.4.0", "cortex_connected": online, "model": CORTEX_MODEL}


@app.get("/status")
async def status():
    online, error = await cortex_online()
    return {
        "name": "X-MIND",
        "version": "0.4.0-conversation",
        "cortex": {"connected": online, "model": CORTEX_MODEL, "error": error},
        "research": {"enabled": SEARCH_ENABLED, "provider": "direct-web"},
        "memory": {"path": str(DB_PATH), "persistent": str(DATA_DIR).startswith("/data")},
        "external_ai_api_required": False,
    }


@app.get("/memories")
def memories(limit: int = 18):
    with db() as c:
        rows = c.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 50),)).fetchall()
    return [dict(r) for r in rows]


@app.post("/chat")
async def chat(req: ChatRequest):
    session = req.session_id or uuid.uuid4().hex
    online, error = await cortex_online()
    if not online:
        raise HTTPException(503, detail={"message": "Local X-MIND cortex is warming up or unavailable.", "error": error})

    user_text = req.message.strip()
    stored_id = None
    mem_text = explicit_memory(user_text)
    if mem_text:
        stored_id = remember(mem_text, "preference", .84)

    casual = is_greeting_or_smalltalk(user_text) and not req.force_research
    do_research = needs_research(user_text, req.force_research) and not casual
    recent = history(session, 6)

    memories_used = [] if casual else recall(user_text, 3)
    memory_block = "\n".join(f"- {clean_text(m['content'], 220)}" for m in memories_used)

    sources = []
    research_block = ""
    if do_research:
        try:
            results = await web_search(user_text, 4)
            if results:
                sources = [x["url"] for x in results if x.get("url")]
                research_block = "\n".join(f"- {x['title']}: {x['snippet']} ({x['url']})" for x in results)
        except Exception:
            research_block = ""

    system = CASUAL_SYSTEM if casual else AGENT_SYSTEM
    extras = []
    if memory_block:
        extras.append("Relevant long-term memory:\n" + memory_block)
    if research_block:
        extras.append("Fresh web research:\n" + research_block)
    if extras:
        system += "\n\n" + "\n\n".join(extras)

    msgs = [{"role": "system", "content": system}, *recent, {"role": "user", "content": user_text}]
    max_tokens = 90 if casual else 260
    temperature = .78 if casual else .62
    m = await cortex(msgs, max_tokens=max_tokens, temperature=temperature)
    answer = clean_text(m.get("content") or "", 4000)
    if not answer:
        answer = "أنا معاك. قولها تاني بصيغة أبسط شوية."

    add_message(session, "user", user_text)
    add_message(session, "assistant", answer)

    return {
        "session_id": session,
        "answer": answer,
        "model": CORTEX_MODEL,
        "mode": "conversation" if casual else ("research" if do_research else "assistant"),
        "memory_used": memories_used,
        "memory_stored": stored_id,
        "sources": list(dict.fromkeys(sources))[:8],
    }


HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>X-MIND</title><style>
:root{--bg:#040713;--card:#0a1020cc;--line:#ffffff18;--text:#edf6ff;--muted:#8ea0bc;--cyan:#5be0ff;--violet:#8c68ff;--green:#67edaa;--red:#ff7e97}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#113756,transparent 30%),radial-gradient(circle at 85% 5%,#321b65,transparent 30%),linear-gradient(180deg,#02040a,#07101e 55%,#02040a);color:var(--text);font-family:Inter,system-ui;min-height:100vh}.wrap{max-width:1280px;margin:auto;padding:16px}.top{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:16px}.brand{display:flex;gap:14px;align-items:center}.orbbox{width:68px;height:68px;perspective:600px}.orb{width:68px;height:68px;border-radius:50%;background:radial-gradient(circle at 30% 24%,#fff,#79e8ff 14%,#3b7cff 38%,#43228a 68%,#050816);box-shadow:0 0 42px #59d8ff66,inset -14px -18px 25px #000a;animation:spin 7s linear infinite}h1{margin:0;letter-spacing:.09em;font-size:27px}.sub{font-size:12px;color:var(--muted)}.grid{display:grid;grid-template-columns:1.55fr .7fr;gap:16px}.card{border:1px solid var(--line);border-radius:24px;background:linear-gradient(145deg,#ffffff10,#ffffff05);backdrop-filter:blur(16px);box-shadow:0 24px 65px #0007}.pad{padding:16px}.head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}.buttons{display:flex;gap:8px}.btn{border:0;border-radius:14px;padding:10px 13px;color:white;font-weight:700;background:linear-gradient(135deg,var(--cyan),var(--violet));cursor:pointer}.ghost{background:#ffffff0d;border:1px solid var(--line)}.chat{height:min(64vh,650px);min-height:430px;overflow:auto;display:grid;align-content:start;gap:10px}.msg{padding:13px 15px;border-radius:18px;border:1px solid var(--line);background:#08101dce;white-space:pre-wrap;line-height:1.55}.you{background:linear-gradient(140deg,#147da72d,#7045c631)}.meta{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-bottom:6px}.input{display:flex;gap:9px;margin-top:12px}textarea{flex:1;min-height:66px;padding:13px;border-radius:16px;border:1px solid var(--line);background:#030712;color:var(--text);resize:vertical}.side{display:grid;gap:16px;align-content:start}.stat{padding:12px;border:1px solid var(--line);border-radius:16px;background:#07101caa}.stat strong{display:block;margin-top:4px}.green{color:var(--green)}.red{color:var(--red)}.mem{display:grid;gap:8px;max-height:330px;overflow:auto}.item{padding:11px;border:1px solid var(--line);border-radius:15px;background:#07101caa}.src{display:block;color:#88ddff;word-break:break-all;margin-top:6px}@keyframes spin{to{transform:rotateY(360deg) rotateX(8deg)}}@media(max-width:880px){.grid{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}@media(max-width:600px){.wrap{padding:10px}.input{flex-direction:column}}
</style></head><body><div class="wrap"><div class="top"><div class="brand"><div class="orbbox"><div class="orb"></div></div><div><h1>X-MIND</h1><div class="sub">CONVERSATION CORE · LOCAL QWEN · PERSISTENT MEMORY · DIRECT RESEARCH</div></div></div><div class="buttons"><button class="btn ghost" onclick="newSession()">New conversation</button><button class="btn ghost" onclick="status()">Core status</button></div></div><div class="grid"><section class="card"><div class="pad"><div class="head"><div><b>COMMAND CHANNEL</b><div class="sub">Talk normally. X-MIND switches modes only when needed.</div></div><span id="mode" class="sub">CONVERSATION</span></div><div id="chat" class="chat"><div class="msg"><div class="meta"><span>X-MIND</span><span>READY</span></div>أنا معاك. كلمني عادي.</div></div><div class="input"><textarea id="q" placeholder="قول لـ X-MIND أي حاجة…"></textarea><button id="send" class="btn" onclick="ask()">Send</button></div></div></section><div class="side"><section class="card"><div class="pad"><b>CORE STATE</b><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px"><div class="stat"><span class="sub">Cortex</span><strong id="conn">checking…</strong></div><div class="stat"><span class="sub">Model</span><strong id="model">—</strong></div><div class="stat"><span class="sub">Memory</span><strong id="persist">—</strong></div><div class="stat"><span class="sub">AI API</span><strong class="green">NONE</strong></div></div></div></section><section class="card"><div class="pad"><div class="head"><div><b>LONG-TERM MEMORY</b><div class="sub">Only durable things worth keeping</div></div><button class="btn ghost" onclick="memory()">Refresh</button></div><div id="mem" class="mem"></div></div></section><section class="card"><div class="pad"><b>SOURCES</b><div id="sources" class="sub" style="margin-top:8px">No research this turn.</div></div></section></div></div></div><script>
const KEY='xmind_session_v4';let session=localStorage.getItem(KEY)||'';const C=document.getElementById('chat'),Q=document.getElementById('q'),S=document.getElementById('send');const E=s=>(s||'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));function add(w,t){const d=document.createElement('div');d.className='msg '+(w==='You'?'you':'');d.innerHTML=`<div class="meta"><span>${w}</span><span>${new Date().toLocaleTimeString()}</span></div>${E(t)}`;C.appendChild(d);C.scrollTop=C.scrollHeight}function newSession(){session='';localStorage.removeItem(KEY);C.innerHTML='<div class="msg"><div class="meta"><span>X-MIND</span><span>NEW</span></div>جلسة جديدة. أنا معاك.</div>';document.getElementById('mode').textContent='CONVERSATION';document.getElementById('sources').textContent='No research this turn.'}async function status(){try{const d=await(await fetch('/status')).json();conn.textContent=d.cortex.connected?'ONLINE':'OFFLINE';conn.className=d.cortex.connected?'green':'red';model.textContent=d.cortex.model;persist.textContent=d.memory.persistent?'PERSISTENT':'TEMP'}catch(e){conn.textContent='ERROR'}}async function memory(){try{const d=await(await fetch('/memories?limit=14')).json();mem.innerHTML=d.length?d.map(x=>`<div class="item"><div class="sub">${E(x.kind)}</div>${E(x.content)}</div>`).join(''):'<div class="item">No long-term memories yet.</div>'}catch(e){}}async function ask(){const t=Q.value.trim();if(!t)return;add('You',t);Q.value='';S.disabled=true;S.textContent='Thinking…';try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t,session_id:session||null})});const d=await r.json();if(!r.ok)throw Error(d.detail?.message||JSON.stringify(d.detail));session=d.session_id;localStorage.setItem(KEY,session);add('X-MIND',d.answer);document.getElementById('mode').textContent=(d.mode||'assistant').toUpperCase();sources.innerHTML=(d.sources||[]).length?d.sources.map(u=>`<a class="src" href="${E(u)}" target="_blank">${E(u)}</a>`).join(''):'No research this turn.';memory()}catch(e){add('X-MIND','Core error: '+e.message)}finally{S.disabled=false;S.textContent='Send';status()}}Q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});status();memory();
</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sovereign_v2:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
