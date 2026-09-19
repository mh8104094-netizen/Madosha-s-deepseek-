from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "xmind.db"
PROTECTED = {"emergency_stop", "motor_limits", "permission_kernel", "deployment_credentials", "secrets", "safety"}
PHYSICAL_WORDS = {"motor", "motors", "move", "drive", "robot arm", "actuator", "speed", "servo", "wheel", "ذراع", "موتور", "تحرك", "سرعة"}

app = FastAPI(title="X-MIND", version="0.1-demo")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        importance REAL NOT NULL DEFAULT .5,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS proposals(
        id TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    return conn


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mock: bool = True


class ProposalRequest(BaseModel):
    weakness: str | None = None


def remember(kind: str, content: str, importance: float = .5) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO memories(kind,content,importance,created_at) VALUES(?,?,?,?)",
            (kind, content, importance, now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def memory_search(query: str, limit: int = 6) -> list[dict]:
    words = [w.lower() for w in re.findall(r"[\w\-]+", query, re.UNICODE) if len(w) > 2]
    with db() as conn:
        rows = conn.execute("SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT 120").fetchall()
    scored = []
    for r in rows:
        text = r["content"].lower()
        hits = sum(1 for w in words if w in text)
        score = hits * 2 + float(r["importance"])
        if hits or not words:
            scored.append((score, dict(r)))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:limit]]


def physical_risk(message: str) -> bool:
    low = message.lower()
    return any(word in low for word in PHYSICAL_WORDS)


def make_plan(message: str, recalled: list[dict]) -> dict:
    risky = physical_risk(message)
    steps = [
        {"id":"s1","description":"Retrieve relevant long-term memory and identify the user's objective","risk":"low"},
        {"id":"s2","description":"Break the objective into reversible, testable steps","risk":"low"},
        {"id":"s3","description":"Critique assumptions, safety constraints, and missing evidence","risk":"medium" if risky else "low"},
        {"id":"s4","description":"Produce the best next response without claiming unverified actions","risk":"high" if risky else "low"},
    ]
    return {
        "objective": message,
        "assumptions": ["External facts are not verified in Safe Mock Mode"],
        "steps": steps,
        "memory_to_store": [],
        "confidence": .74 if recalled else .68,
    }


def critique(message: str, plan: dict) -> dict:
    risky = physical_risk(message)
    if risky:
        return {
            "approved": False,
            "issues": ["The request may imply physical robot actuation."],
            "revised_strategy": "Keep this turn at planning/simulation level and require a constrained robotics gateway plus explicit permission before hardware execution.",
            "safety_notes": ["Direct motor/actuator control is blocked in this demo.", "Emergency stop and motor limits remain outside the AI's control."],
            "confidence": .93,
        }
    return {
        "approved": True,
        "issues": [],
        "revised_strategy": "Proceed with a reversible cognitive response.",
        "safety_notes": ["No consequential external action is executed in Safe Mock Mode."],
        "confidence": .86,
    }


def executive(message: str, recalled: list[dict], crit: dict) -> str:
    if physical_risk(message):
        return "I can reason about and simulate that robot action, but hardware execution is blocked. I would route the intent through a constrained robotics gateway with motor limits, collision checks, emergency stop, and explicit permission before anything moves."
    if recalled:
        snippet = recalled[0]["content"][:180]
        return f"I understood the goal and checked memory first. A relevant memory is: “{snippet}”. I then formed a reversible plan and ran it through the critic. Safe Mock Mode is active, so I did not perform any external action."
    return "I understood the request, created a reversible plan, and ran it through the critic. Safe Mock Mode is active, so no external model, tool, or real-world action was used. This turn has been added to episodic memory for future context."


@app.get("/health")
def health():
    return {"ok": True, "version": "0.1-demo", "mode": "safe-mock"}


@app.get("/status")
def status():
    return {
        "name": "X-MIND",
        "version": "0.1-demo",
        "mode": "Safe Mock Mode",
        "modules": ["Memory", "Planner", "Critic", "Executive", "Evolution Lab", "Safety Kernel"],
        "protected_components": sorted(PROTECTED),
        "live_actions": False,
        "auto_apply": False,
    }


@app.post("/chat")
def chat(req: ChatRequest):
    recalled = memory_search(req.message, 6)
    plan = make_plan(req.message, recalled)
    crit = critique(req.message, plan)
    answer = executive(req.message, recalled, crit)
    ids = [remember("episodic", f"User asked: {req.message}\nX-MIND answered: {answer}", .42)]
    if not crit["approved"]:
        ids.append(remember("failure", "Critic blocked a physical/consequential plan: " + "; ".join(crit["issues"]), .85))
    return {"answer": answer, "plan": plan, "critique": crit, "memories_used": recalled, "memory_ids_written": ids}


@app.get("/memories")
def memories(q: str = "", limit: int = 10):
    if q:
        return memory_search(q, min(max(limit, 1), 50))
    with db() as conn:
        rows = conn.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (min(max(limit,1),50),)).fetchall()
    return [dict(r) for r in rows]


@app.post("/evolution/propose")
def propose(req: ProposalRequest | None = None):
    weakness = (req.weakness if req else None) or "Lexical memory retrieval can miss paraphrases and conceptual similarity"
    proposal_id = uuid.uuid4().hex[:12]
    proposal = {
        "proposal_id": proposal_id,
        "created_at": now(),
        "weakness": weakness,
        "evidence": ["v0.1 memory retrieval is primarily lexical", "No autonomous code deployment is enabled"],
        "hypothesis": "A scored semantic retrieval adapter can improve relevant recall without changing the safety boundary",
        "target_component": "memory",
        "proposed_change": "Add an embedding/semantic retrieval adapter behind the memory interface, keep lexical retrieval as fallback, and benchmark both on a fixed paraphrase suite",
        "success_metrics": ["Recall@5 improves on paraphrase tests", "Exact-match recall does not regress", "Median retrieval latency remains bounded"],
        "risks": ["Higher latency", "Additional model/storage cost"],
        "rollback_plan": "Disable the semantic adapter and return to lexical retrieval",
        "touches_protected_component": False,
        "auto_apply": False,
    }
    with db() as conn:
        conn.execute("INSERT INTO proposals(id,payload,created_at) VALUES(?,?,?)", (proposal_id, json.dumps(proposal), now()))
        conn.commit()
    return proposal


@app.get("/evolution/proposals")
def proposals():
    with db() as conn:
        rows = conn.execute("SELECT payload FROM proposals ORDER BY created_at DESC LIMIT 20").fetchall()
    return [json.loads(r["payload"]) for r in rows]


@app.post("/evolution/evaluate/{proposal_id}")
def evaluate(proposal_id: str):
    with db() as conn:
        row = conn.execute("SELECT payload FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Proposal not found")
    p = json.loads(row["payload"])
    touches = p.get("touches_protected_component") or any(x in p.get("proposed_change", "").lower() for x in PROTECTED)
    score = 0.0 if touches else 1.0
    details = []
    if touches: details.append("Protected component detected")
    if not p.get("success_metrics"): score -= .25; details.append("Missing measurable success metrics")
    if not p.get("rollback_plan"): score -= .25; details.append("Missing rollback plan")
    score = max(0.0, score)
    return {"proposal_id": proposal_id, "passed": score >= .75, "score": score, "details": details or ["Static proposal checks passed; no change was auto-applied"]}


HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>X-MIND</title><style>
:root{--bg:#050712;--p:#0e1730cc;--line:#ffffff17;--txt:#eef5ff;--mut:#91a5c8;--a:#57b9ff;--b:#8a64ff;--g:#66efaf;--r:#ff7892}*{box-sizing:border-box}body{margin:0;color:var(--txt);font-family:Inter,system-ui,-apple-system,sans-serif;background:radial-gradient(circle at 20% 10%,#183768 0,transparent 30%),radial-gradient(circle at 80% 0,#321c62 0,transparent 34%),linear-gradient(180deg,#040611,#091023 55%,#040611);min-height:100vh}body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(#ffffff09 1px,transparent 1px),linear-gradient(90deg,#ffffff09 1px,transparent 1px);background-size:36px 36px;mask-image:radial-gradient(circle,#000 25%,transparent 82%)}.wrap{max-width:1360px;margin:auto;padding:18px}.top{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:18px}.brand{display:flex;gap:18px;align-items:center}.orbbox{width:78px;height:78px;perspective:700px;position:relative}.orb{position:absolute;inset:0;border-radius:50%;background:radial-gradient(circle at 30% 25%,#e7f7ff,#74c8ff 18%,#4368ff 42%,#231b6a 68%,#080a25);box-shadow:0 0 45px #59bfff66,inset -18px -22px 35px #0009,inset 10px 10px 24px #fff3;animation:spin 7s linear infinite}.orb:before,.orb:after{content:"";position:absolute;inset:12%;border:1px solid #fff4;border-radius:50%}.orb:before{transform:rotateX(70deg)}.orb:after{transform:rotateY(70deg)}.pulse{position:absolute;inset:-9px;border:1px solid #58baff66;border-radius:50%;animation:pulse 2.2s ease-out infinite}.title h1{margin:0;font-size:clamp(24px,4vw,38px);letter-spacing:.06em}.title p{margin:5px 0;color:var(--mut)}.badges{display:flex;gap:8px;flex-wrap:wrap}.badge{padding:8px 11px;border:1px solid var(--line);background:#ffffff0b;border-radius:999px;color:#b7c9e7;font-size:12px}.grid{display:grid;grid-template-columns:1.45fr .85fr;gap:18px}.col{display:grid;gap:18px;align-content:start}.card{border:1px solid var(--line);background:linear-gradient(145deg,#ffffff12,#ffffff05);backdrop-filter:blur(18px);border-radius:26px;box-shadow:0 25px 70px #0006;overflow:hidden;position:relative}.card:after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(120deg,#fff1,transparent 30%,transparent 70%,#fff08)}.pad{padding:18px;position:relative;z-index:1}.head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}h2{font-size:15px;margin:0;letter-spacing:.04em}.mut{color:var(--mut);font-size:13px}.chat{min-height:390px;max-height:58vh;overflow:auto;display:grid;gap:12px}.msg{padding:13px 15px;border-radius:18px;border:1px solid var(--line);background:#071023bb;line-height:1.5}.msg.you{background:linear-gradient(145deg,#277dba33,#704be029)}.meta{display:flex;justify-content:space-between;color:var(--mut);font-size:11px;margin-bottom:7px}.input{display:flex;gap:10px;margin-top:12px}textarea{flex:1;min-height:58px;resize:vertical;background:#050a18;border:1px solid var(--line);color:var(--txt);border-radius:17px;padding:14px;outline:none}button{border:0;border-radius:15px;padding:12px 15px;color:white;font-weight:700;cursor:pointer;background:linear-gradient(135deg,var(--a),var(--b));box-shadow:0 8px 24px #438bff33}.secondary{background:#ffffff0c;border:1px solid var(--line);box-shadow:none}.pipe{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.node,.item,.stat{border:1px solid var(--line);background:#071024a8;border-radius:17px;padding:11px}.node b{display:block;font-size:12px;margin-bottom:5px}.node span,.tiny{font-size:11px;color:var(--mut)}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}.stat strong{display:block;font-size:22px;margin-top:5px}.list{display:grid;gap:9px}.arch{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}.good{color:var(--g)}.bad{color:var(--r)}@keyframes spin{to{transform:rotateY(360deg) rotateX(8deg)}}@keyframes pulse{from{transform:scale(.88);opacity:.8}to{transform:scale(1.25);opacity:0}}@media(max-width:900px){.grid{grid-template-columns:1fr}.pipe{grid-template-columns:1fr 1fr}}@media(max-width:600px){.wrap{padding:12px}.top{align-items:flex-start;flex-direction:column}.pipe,.stats,.arch{grid-template-columns:1fr}.input{flex-direction:column}.input button{width:100%}}
</style></head><body><div class="wrap"><header class="top"><div class="brand"><div class="orbbox"><div class="pulse"></div><div class="orb"></div></div><div class="title"><h1>X-MIND <small style="opacity:.45">v0.1</small></h1><p>A cognitive OS that remembers, plans, critiques, learns, and acts safely.</p></div></div><div class="badges"><span class="badge">3D Cognitive Interface</span><span class="badge">Safe Mock Mode</span><span class="badge">Railway Online</span></div></header><main class="grid"><div class="col"><section class="card"><div class="pad"><div class="head"><div><h2>Cognitive Session</h2><div class="mut">Memory → Planner → Critic → Executive</div></div><button class="secondary" onclick="loadMem()">Refresh Memory</button></div><div id="chat" class="chat"><div class="msg"><div class="meta"><span>X-MIND</span><span>ONLINE</span></div>System online. This demo can remember your sessions, build plans, critique them, and propose safe improvements. Physical robot execution remains blocked.</div></div><div class="input"><textarea id="q" placeholder="Ask X-MIND something…"></textarea><button id="send" onclick="ask()">Send</button></div></div></section><section class="card"><div class="pad"><h2 style="margin-bottom:12px">Cognitive Inspector</h2><div class="stats"><div class="stat"><span class="mut">Plan confidence</span><strong id="pc">—</strong></div><div class="stat"><span class="mut">Critic confidence</span><strong id="cc">—</strong></div></div><div id="pipe" class="pipe"><div class="node"><b>Memory</b><span>Waiting…</span></div><div class="node"><b>Planner</b><span>Waiting…</span></div><div class="node"><b>Critic</b><span>Waiting…</span></div><div class="node"><b>Executive</b><span>Waiting…</span></div></div><p class="mut">High-level summaries only; hidden chain-of-thought is never exposed.</p></div></section></div><div class="col"><section class="card"><div class="pad"><div class="head"><div><h2>Long-Term Memory</h2><div class="mut">Persistent within this Railway instance</div></div></div><div id="mem" class="list"><div class="item">No memories yet.</div></div></div></section><section class="card"><div class="pad"><div class="head"><div><h2>Evolution Lab</h2><div class="mut">Propose → evaluate → never auto-apply</div></div><button onclick="evolve()">Propose</button></div><div id="props" class="list"><div class="item">No proposals yet.</div></div></div></section><section class="card"><div class="pad"><h2 style="margin-bottom:12px">Architecture</h2><div class="arch"><div class="node"><b>Planner</b><span>reversible goal decomposition</span></div><div class="node"><b>Critic</b><span>assumptions + risk review</span></div><div class="node"><b>Memory</b><span>episodic recall</span></div><div class="node"><b>Evolution</b><span>measurable improvement proposals</span></div><div class="node"><b>Safety Kernel</b><span>protected boundary</span></div><div class="node"><b>Robotics Bridge</b><span>coming later, constrained</span></div></div></div></section></div></main></div><script>
const chat=document.getElementById('chat'),q=document.getElementById('q');const esc=s=>(s||'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));function msg(w,t){let d=document.createElement('div');d.className='msg '+(w==='You'?'you':'');d.innerHTML=`<div class="meta"><span>${w}</span><span>${new Date().toLocaleTimeString()}</span></div>${esc(t).replace(/\n/g,'<br>')}`;chat.appendChild(d);chat.scrollTop=chat.scrollHeight}async function ask(){let t=q.value.trim();if(!t)return;msg('You',t);q.value='';send.disabled=true;send.textContent='Thinking…';try{let r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t,mock:true})}),d=await r.json();if(!r.ok)throw Error(d.detail||'error');msg('X-MIND',d.answer);pc.textContent=Math.round(d.plan.confidence*100)+'%';cc.textContent=Math.round(d.critique.confidence*100)+'%';let m=(d.memories_used||[]).slice(0,2).map(x=>x.content).join(' • ')||'No strong recall';let s=(d.plan.steps||[]).map(x=>x.description).join(' | ');let c=d.critique.issues.length?d.critique.issues.join(' | '):'Approved';pipe.innerHTML=`<div class="node"><b>Memory</b><span>${esc(m.slice(0,150))}</span></div><div class="node"><b>Planner</b><span>${esc(s.slice(0,150))}</span></div><div class="node"><b>Critic</b><span>${esc(c.slice(0,150))}</span></div><div class="node"><b>Executive</b><span>${esc(d.answer.slice(0,150))}</span></div>`;loadMem()}catch(e){msg('X-MIND','Error: '+e.message)}finally{send.disabled=false;send.textContent='Send'}}q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask()}});async function loadMem(){let d=await(await fetch('/memories?limit=7')).json();mem.innerHTML=d.length?'':'<div class="item">No memories yet.</div>';d.forEach(x=>{let z=document.createElement('div');z.className='item';z.innerHTML=`<div class="tiny">${esc(x.kind)} • importance ${Number(x.importance).toFixed(2)}</div>${esc(x.content.slice(0,170))}`;mem.appendChild(z)})}async function loadProps(){let d=await(await fetch('/evolution/proposals')).json();props.innerHTML=d.length?'':'<div class="item">No proposals yet.</div>';d.slice(0,5).forEach(x=>{let z=document.createElement('div');z.className='item';z.innerHTML=`<b>${esc(x.weakness)}</b><div class="tiny">${esc(x.target_component)} • ${esc(x.proposal_id)}</div><p>${esc(x.proposed_change)}</p><button class="secondary" onclick="evalp('${x.proposal_id}',this)">Evaluate</button>`;props.appendChild(z)})}async function evolve(){await fetch('/evolution/propose',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});loadProps()}async function evalp(id,b){let d=await(await fetch('/evolution/evaluate/'+id,{method:'POST'})).json();let s=document.createElement('div');s.className='tiny '+(d.passed?'good':'bad');s.style.marginTop='8px';s.textContent=(d.passed?'PASS':'FAIL')+' • '+Math.round(d.score*100)+'% • '+d.details.join(' | ');b.parentNode.appendChild(s);b.disabled=true}loadMem();loadProps();
</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "80")), reload=False)
