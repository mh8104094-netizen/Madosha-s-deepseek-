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
CORTEX_MODEL = os.getenv("XMIND_CORTEX_MODEL", "qwen3:30b-a3b")
SEARCH_ENABLED = os.getenv("XMIND_SEARCH_ENABLED", "true").lower() == "true"
MAX_TOOL_ROUNDS = int(os.getenv("XMIND_MAX_TOOL_ROUNDS", "5"))
UA = "Mozilla/5.0 X-MIND Sovereign Research Agent"

app = FastAPI(title="X-MIND Sovereign Core", version="0.3.0")


def now(): return datetime.now(timezone.utc).isoformat()


def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, content TEXT NOT NULL, importance REAL NOT NULL DEFAULT .5, created_at TEXT NOT NULL, use_count INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS research_cache(key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL)")
    c.commit(); return c


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    session_id: str | None = None
    force_research: bool = False

class MemoryRequest(BaseModel):
    content: str
    kind: str = "semantic"
    importance: float = Field(default=.7, ge=0, le=1)


def tokens(s):
    return {x.lower() for x in re.findall(r"[\w\-]+", s, re.UNICODE) if len(x) >= 2}


def remember(content, kind="semantic", importance=.7):
    content = re.sub(r"\s+", " ", content).strip()
    with db() as c:
        old = c.execute("SELECT id FROM memories WHERE lower(content)=lower(?) LIMIT 1", (content,)).fetchone()
        if old:
            c.execute("UPDATE memories SET importance=max(importance,?), use_count=use_count+1 WHERE id=?", (importance, old["id"])); c.commit(); return int(old["id"])
        cur = c.execute("INSERT INTO memories(kind,content,importance,created_at,use_count) VALUES(?,?,?,?,0)", (kind,content,importance,now())); c.commit(); return int(cur.lastrowid)


def recall(query, limit=8):
    q=tokens(query)
    with db() as c: rows=c.execute("SELECT * FROM memories ORDER BY importance DESC,id DESC LIMIT 350").fetchall()
    scored=[]
    for r in rows:
        d=dict(r); ov=len(q & tokens(d["content"])); ph=2 if query.lower() in d["content"].lower() else 0
        score=ov*1.8+ph+float(d["importance"])+min(d["use_count"]*.03,.3)
        if ov or ph or not q: scored.append((score,d))
    scored.sort(key=lambda x:x[0], reverse=True)
    out=[x[1] for x in scored[:limit]]
    if out:
        ids=[x["id"] for x in out]; marks=",".join("?" for _ in ids)
        with db() as c: c.execute(f"UPDATE memories SET use_count=use_count+1 WHERE id IN ({marks})", ids); c.commit()
    return out


def add_message(session_id, role, content):
    with db() as c: c.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)", (session_id,role,content,now())); c.commit()


def history(session_id, limit=18):
    with db() as c: rows=c.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id,limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def unwrap(href):
    try:
        q=parse_qs(urlparse(href).query)
        return unquote(q["uddg"][0]) if "uddg" in q else href
    except Exception: return href


async def web_search(query, max_results=6):
    if not SEARCH_ENABLED: return [{"title":"Research disabled","url":"","snippet":"XMIND_SEARCH_ENABLED=false"}]
    key=f"s:{query.lower()}:{max_results}"
    with db() as c: cached=c.execute("SELECT payload,created_at FROM research_cache WHERE key=?",(key,)).fetchone()
    if cached and time.time()-cached["created_at"]<900: return json.loads(cached["payload"])
    async with httpx.AsyncClient(headers={"User-Agent":UA},timeout=20,follow_redirects=True) as client:
        r=await client.get("https://html.duckduckgo.com/html/",params={"q":query}); r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser"); out=[]
    for result in soup.select(".result"):
        a=result.select_one("a.result__a")
        if not a: continue
        sn=result.select_one(".result__snippet")
        out.append({"title":a.get_text(" ",strip=True),"url":unwrap(a.get("href","")),"snippet":sn.get_text(" ",strip=True) if sn else ""})
        if len(out)>=max_results: break
    with db() as c: c.execute("INSERT OR REPLACE INTO research_cache(key,payload,created_at) VALUES(?,?,?)",(key,json.dumps(out,ensure_ascii=False),time.time())); c.commit()
    return out


TOOLS=[
 {"type":"function","function":{"name":"web_search","description":"Search the public web when information may be current, niche, or needs verification.","parameters":{"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"integer","minimum":1,"maximum":8}},"required":["query"]}}},
 {"type":"function","function":{"name":"remember","description":"Store a stable user preference, project fact, correction, decision, workflow, or important long-term detail.","parameters":{"type":"object","properties":{"content":{"type":"string"},"kind":{"type":"string","enum":["semantic","preference","decision","project","failure"]},"importance":{"type":"number","minimum":0,"maximum":1}},"required":["content"]}}},
 {"type":"function","function":{"name":"recall_memory","description":"Search X-MIND long-term memory.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}}
]

SYSTEM="""You are X-MIND, a sovereign personal AI operating system and the user's right-hand assistant. Qwen is only your current cortex, not your identity. Speak naturally in the user's language. Be proactive, precise, capable and practical. Use web_search when information may be current or uncertain. Use recall_memory when past project context may help. Use remember for stable preferences, project decisions, corrections and workflows that will matter later. Never claim you searched, remembered, executed or read something unless the tool actually succeeded. Never expose hidden chain-of-thought; give concise reasoning summaries only when useful. For web-researched answers, include a short Sources section with the URLs you actually used. Consequential physical actions are never executed directly by the language model; robotics must pass through a constrained external permission and safety gateway. Safety kernel, emergency stop, motor limits, credentials and deployment secrets are never self-modified."""


async def cortex_online():
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            r=await client.get(CORTEX_URL+"/api/tags"); r.raise_for_status()
        return True,None
    except Exception as e: return False,str(e)[:250]


async def cortex(messages, tools=None):
    payload={"model":CORTEX_MODEL,"messages":messages,"stream":False,"options":{"temperature":.6,"top_p":.95,"num_ctx":32768}}
    if tools: payload["tools"]=tools
    async with httpx.AsyncClient(timeout=180) as client:
        r=await client.post(CORTEX_URL+"/api/chat",json=payload); r.raise_for_status(); return r.json().get("message",{})


def parse_call(call):
    fn=call.get("function",{}); name=fn.get("name",""); args=fn.get("arguments",{})
    if isinstance(args,str):
        try: args=json.loads(args)
        except Exception: args={}
    return name,args


async def run_tool(name,args):
    if name=="web_search": return await web_search(str(args.get("query","")),int(args.get("max_results",6)))
    if name=="remember": return {"stored":True,"memory_id":remember(str(args.get("content","")),str(args.get("kind","semantic")),float(args.get("importance",.72)))}
    if name=="recall_memory": return recall(str(args.get("query","")),8)
    return {"error":"unknown tool"}


@app.get("/health")
async def health():
    online,_=await cortex_online(); return {"ok":True,"version":"0.3.0","cortex_connected":online,"model":CORTEX_MODEL}

@app.get("/status")
async def status():
    online,error=await cortex_online()
    return {"name":"X-MIND","version":"0.3.0-sovereign","cortex":{"connected":online,"url":CORTEX_URL,"model":CORTEX_MODEL,"error":error},"research":{"enabled":SEARCH_ENABLED,"provider":"direct-web"},"external_ai_api_required":False}

@app.get("/memories")
def memories(q:str="",limit:int=30):
    if q:return recall(q,min(max(limit,1),100))
    with db() as c: rows=c.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?",(min(max(limit,1),100),)).fetchall()
    return [dict(r) for r in rows]

@app.post("/memory")
def memory(req:MemoryRequest): return {"stored":True,"id":remember(req.content,req.kind,req.importance)}

@app.post("/chat")
async def chat(req:ChatRequest):
    session=req.session_id or uuid.uuid4().hex
    online,error=await cortex_online()
    if not online: raise HTTPException(503,detail={"message":"X-MIND Sovereign Core is installed but the self-hosted Qwen cortex is not connected.","expected_url":CORTEX_URL,"model":CORTEX_MODEL,"error":error})
    mem=recall(req.message,8); memtxt="\n".join(f"- [{m['kind']}] {m['content']}" for m in mem) or "- none"
    msgs=[{"role":"system","content":SYSTEM+"\nRelevant long-term memory:\n"+memtxt},*history(session)]
    user=req.message+("\nResearch the web before answering." if req.force_research else "")
    msgs.append({"role":"user","content":user}); tools_used=[]; sources=[]; answer=""
    for _ in range(MAX_TOOL_ROUNDS):
        m=await cortex(msgs,TOOLS); calls=m.get("tool_calls") or []; content=m.get("content") or ""
        if not calls: answer=content.strip(); break
        msgs.append({"role":"assistant","content":content,"tool_calls":calls})
        for call in calls:
            name,args=parse_call(call)
            try: result=await run_tool(name,args)
            except Exception as e: result={"error":str(e)[:400]}
            tools_used.append({"name":name,"args":args,"preview":json.dumps(result,ensure_ascii=False)[:900]})
            if name=="web_search" and isinstance(result,list): sources += [x.get("url","") for x in result if x.get("url")]
            msgs.append({"role":"tool","tool_name":name,"content":json.dumps(result,ensure_ascii=False)})
    if not answer: answer="I reached the tool-iteration limit before producing a final answer."
    add_message(session,"user",req.message); add_message(session,"assistant",answer)
    return {"session_id":session,"answer":answer,"model":CORTEX_MODEL,"memory_used":mem,"tools_used":tools_used,"sources":list(dict.fromkeys(sources))[:12]}

HTML='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>X-MIND</title><style>:root{--b:#050713;--p:#0c1428cc;--l:#ffffff18;--t:#eef5ff;--m:#92a4c0;--c:#59d9ff;--v:#8a66ff;--g:#60e8a6;--r:#ff8096}*{box-sizing:border-box}body{margin:0;min-height:100vh;color:var(--t);font-family:Inter,system-ui;background:radial-gradient(circle at 20% 8%,#123d5b,transparent 28%),radial-gradient(circle at 80% 0,#2f185f,transparent 33%),linear-gradient(180deg,#03040a,#090e1c 55%,#03040a)}.w{max-width:1400px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:18px}.brand{display:flex;gap:16px;align-items:center}.ob{width:82px;height:82px;position:relative;perspective:800px}.orb{position:absolute;inset:0;border-radius:50%;background:radial-gradient(circle at 28% 25%,#effcff,#6bdcff 16%,#3871ff 39%,#341e83 65%,#070a20);box-shadow:0 0 54px #59d8ff66,inset -20px -24px 38px #0009,inset 12px 12px 22px #fff3;animation:s 8s linear infinite}.orb:before,.orb:after{content:"";position:absolute;inset:13%;border:1px solid #fff4;border-radius:50%}.orb:before{transform:rotateX(68deg)}.orb:after{transform:rotateY(68deg)}h1{margin:0;letter-spacing:.08em}.mut{color:var(--m);font-size:12px}.badges{display:flex;gap:8px;flex-wrap:wrap}.badge{padding:8px 11px;border:1px solid var(--l);border-radius:999px;background:#fff0b;font-size:12px}.grid{display:grid;grid-template-columns:1.5fr .75fr;gap:18px}.col{display:grid;gap:18px;align-content:start}.card{border:1px solid var(--l);background:linear-gradient(145deg,#ffffff10,#ffffff05);backdrop-filter:blur(18px);border-radius:26px;box-shadow:0 25px 70px #0008}.pad{padding:18px}.head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}.chat{height:min(60vh,640px);min-height:430px;overflow:auto;display:grid;gap:11px;align-content:start}.msg{padding:13px 15px;border:1px solid var(--l);background:#07101fcc;border-radius:18px;white-space:pre-wrap;line-height:1.55}.msg.you{background:linear-gradient(140deg,#1c7fa72e,#6b43c82b)}.meta{display:flex;justify-content:space-between;color:var(--m);font-size:11px;margin-bottom:7px}.input{display:flex;gap:10px;margin-top:12px}textarea{flex:1;min-height:64px;background:#040814;color:var(--t);border:1px solid var(--l);border-radius:17px;padding:14px;resize:vertical}button{border:0;border-radius:15px;padding:12px 16px;color:#fff;font-weight:700;background:linear-gradient(135deg,var(--c),var(--v));cursor:pointer}.secondary{background:#fff0b;border:1px solid var(--l)}.stats{display:grid;grid-template-columns:1fr 1fr;gap:9px}.item,.stat{border:1px solid var(--l);background:#07101daa;border-radius:17px;padding:12px}.stat strong{display:block;margin-top:5px}.green{color:var(--g)}.red{color:var(--r)}.mem{display:grid;gap:8px;max-height:360px;overflow:auto}.src{display:block;color:#8fdfff;word-break:break-all;margin-top:5px}@keyframes s{to{transform:rotateY(360deg) rotateX(8deg)}}@media(max-width:900px){.grid{grid-template-columns:1fr}.top{flex-direction:column;align-items:flex-start}}@media(max-width:600px){.w{padding:11px}.input{flex-direction:column}.stats{grid-template-columns:1fr}}</style></head><body><div class="w"><header class="top"><div class="brand"><div class="ob"><div class="orb"></div></div><div><h1>X-MIND</h1><div class="mut">SOVEREIGN CORTEX · LOCAL QWEN · DIRECT RESEARCH · PERSISTENT MEMORY</div></div></div><div class="badges"><span class="badge">NO THIRD-PARTY AI API</span><span class="badge">QWEN CORTEX</span><span class="badge">SELF-HOSTED</span></div></header><main class="grid"><div class="col"><section class="card"><div class="pad"><div class="head"><div><b>COMMAND CHANNEL</b><div class="mut">Recall · reason · research · learn</div></div><button class="secondary" onclick="status()">Core Status</button></div><div id="chat" class="chat"><div class="msg"><div class="meta"><span>X-MIND</span><span>BOOT</span></div>Sovereign core installed. If the Qwen cortex is disconnected, I will say so instead of faking an answer.</div></div><div class="input"><textarea id="q" placeholder="Talk to X-MIND…"></textarea><button id="send" onclick="ask()">Send</button></div></div></section></div><div class="col"><section class="card"><div class="pad"><b>CORTEX STATE</b><div class="stats" style="margin-top:10px"><div class="stat"><span class="mut">Connection</span><strong id="conn">checking…</strong></div><div class="stat"><span class="mut">Model</span><strong id="model">—</strong></div><div class="stat"><span class="mut">Research</span><strong>Direct Web</strong></div><div class="stat"><span class="mut">External AI API</span><strong class="green">NONE</strong></div></div></div></section><section class="card"><div class="pad"><div class="head"><div><b>LONG-TERM MEMORY</b><div class="mut">What X-MIND has retained</div></div><button class="secondary" onclick="memory()">Refresh</button></div><div id="mem" class="mem"></div></div></section><section class="card"><div class="pad"><b>LAST TOOL ACTIVITY</b><div id="tools" class="item mut" style="margin-top:10px">No tools yet.</div><div id="sources" style="margin-top:10px"></div></div></section></div></main></div><script>let session=localStorage.xmind_session||'';const C=document.getElementById('chat'),Q=document.getElementById('q'),S=document.getElementById('send'),E=s=>(s||'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));function add(w,t){let d=document.createElement('div');d.className='msg '+(w==='You'?'you':'');d.innerHTML=`<div class="meta"><span>${w}</span><span>${new Date().toLocaleTimeString()}</span></div>${E(t)}`;C.appendChild(d);C.scrollTop=C.scrollHeight}async function status(){let d=await(await fetch('/status')).json();conn.textContent=d.cortex.connected?'ONLINE':'OFFLINE';conn.className=d.cortex.connected?'green':'red';model.textContent=d.cortex.model}async function memory(){let d=await(await fetch('/memories?limit=18')).json();mem.innerHTML=d.length?d.map(x=>`<div class="item"><div class="mut">${E(x.kind)} · ${Number(x.importance).toFixed(2)}</div>${E(x.content)}</div>`).join(''):'<div class="item">No memories yet.</div>'}async function ask(){let t=Q.value.trim();if(!t)return;add('You',t);Q.value='';S.disabled=true;S.textContent='Thinking…';try{let r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t,session_id:session||null})}),d=await r.json();if(!r.ok)throw Error(d.detail?.message||JSON.stringify(d.detail));session=d.session_id;localStorage.xmind_session=session;add('X-MIND',d.answer);tools.innerHTML=(d.tools_used||[]).length?d.tools_used.map(x=>`<div><b>${E(x.name)}</b> ${E(JSON.stringify(x.args))}</div>`).join(''):'No tools this turn.';sources.innerHTML=(d.sources||[]).length?'<div class="mut">SOURCES</div>'+d.sources.map(u=>`<a class="src" href="${E(u)}" target="_blank">${E(u)}</a>`).join(''):'';memory()}catch(e){add('X-MIND','Core error: '+e.message)}finally{S.disabled=false;S.textContent='Send';status()}}Q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});status();memory();</script></body></html>'''

@app.get("/",response_class=HTMLResponse)
def home(): return HTML

if __name__=="__main__":
    import uvicorn
    uvicorn.run("sovereign:app",host="0.0.0.0",port=int(os.getenv("PORT","8000")),reload=False)
