#!/usr/bin/env python3
"""vibe-stack dashboard — minimal real-time view + control for tmux coding agents.

Single-file, stdlib-only. Shows every tmux agent session, its status
(working / idle / blocked), the last lines of output, and a git-derived
kanban of lanes. Token-protected; control endpoints inject keystrokes via
the CJK-safe paste-buffer method.

Run:   python3 dashboard/server.py
Open:  the URL printed on startup (works over LAN or Tailscale).
Env:   PORT (default 8765), VIBE_REPO (default ~/projects/repo/vibe-stack),
       VIBE_TOKEN (default: generated + stored in ~/.hermes/dashboard.token).
"""
import json, os, re, secrets, subprocess, hashlib, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", "8765"))
REPO = os.path.expanduser(os.environ.get("VIBE_REPO", "~/projects/repo/vibe-stack"))
TOKEN_FILE = os.path.expanduser("~/.hermes/dashboard.token")

def _load_token():
    t = os.environ.get("VIBE_TOKEN")
    if t:
        return t
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE).read().strip()
    t = secrets.token_urlsafe(18)
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(t)
    os.chmod(TOKEN_FILE, 0o600)
    return t

TOKEN = _load_token()

# --- prompt/activity signatures for status heuristic ---
BLOCKED_SIGS = ["❯ 1.", "❯ 2.", "Do you want", "(y/n)", "[y/N]", "Yes, I accept",
                "No, exit", "trust this folder", "Press Enter", "Select an option",
                "1. Yes", "2. No", "approve", "/login", "Waiting for"]
WORKING_SIGS = ["Esc to interrupt", "esc to interrupt", "Running", "Thinking",
                "tokens", "⏵", "●", "✻", "✶", "✳"]

_last_pane = {}  # session -> (hash, ts) to detect activity between polls

def sh(args, timeout=8):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""

def tmux_sessions():
    out = sh(["tmux", "list-sessions", "-F",
              "#{session_name}\t#{session_attached}\t#{session_windows}"])
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 1 and parts[0]:
            rows.append({"name": parts[0],
                         "attached": parts[1] == "1" if len(parts) > 1 else False,
                         "windows": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1})
    return rows

def capture(sess, lines=14):
    return sh(["tmux", "capture-pane", "-t", sess, "-p", "-S", f"-{lines}"])

def status_of(sess, pane):
    text = pane.strip()
    low = text.lower()
    if any(s.lower() in low for s in BLOCKED_SIGS):
        st = "blocked"
    else:
        h = hashlib.md5(pane.encode()).hexdigest()
        prev = _last_pane.get(sess)
        changed = prev is not None and prev[0] != h
        _last_pane[sess] = (h, time.time())
        if any(s in pane for s in WORKING_SIGS) or changed:
            st = "working"
        else:
            st = "idle"
    return st

def agents():
    out = []
    for s in tmux_sessions():
        pane = capture(s["name"])
        tail = [l for l in pane.splitlines() if l.strip()][-8:]
        out.append({**s, "status": status_of(s["name"], pane), "tail": tail})
    return out

def lanes():
    """Derive a kanban from git worktrees + lane/* branches + optional .lanes/*.md."""
    res = []
    wl = sh(["git", "-C", REPO, "worktree", "list", "--porcelain"])
    worktrees = {}  # branch -> path
    cur = {}
    for line in wl.splitlines():
        if line.startswith("worktree "):
            cur = {"path": line.split(" ", 1)[1]}
        elif line.startswith("branch "):
            br = line.split(" ", 1)[1].replace("refs/heads/", "")
            worktrees[br] = cur.get("path", "")
    merged = set(b.strip().lstrip("* ").strip()
                 for b in sh(["git", "-C", REPO, "branch", "--merged", "main"]).splitlines())
    sess_names = {s["name"] for s in tmux_sessions()}
    branches = [b.strip().lstrip("* ").strip()
                for b in sh(["git", "-C", REPO, "for-each-ref",
                             "--format=%(refname:short)", "refs/heads/"]).splitlines()]
    lane_branches = [b for b in branches if b.startswith("lane/") or b.startswith("feature/")]
    for br in lane_branches:
        slug = br.split("/", 1)[1] if "/" in br else br
        has_session = any(slug in n for n in sess_names)
        if br in merged and br != "main":
            state = "done"
        elif has_session:
            state = "in-progress"
        elif br in worktrees:
            state = "review"
        else:
            state = "todo"
        last = sh(["git", "-C", REPO, "log", "-1", "--format=%s", br]).strip()
        res.append({"branch": br, "slug": slug, "state": state,
                    "worktree": worktrees.get(br, ""), "last_commit": last})
    return res

def status_payload():
    return {"agents": agents(), "lanes": lanes(), "generated_at": int(time.time())}

# --- control: CJK-safe text injection via paste-buffer, special keys via send-keys ---
def send_text(sess, text):
    buf = "vsdash"
    p = subprocess.run(["tmux", "load-buffer", "-b", buf, "-"],
                       input=text, text=True, capture_output=True)
    if p.returncode != 0:
        return False
    subprocess.run(["tmux", "paste-buffer", "-t", sess, "-b", buf, "-d"], capture_output=True)
    subprocess.run(["tmux", "send-keys", "-t", sess, "C-m"], capture_output=True)
    return True

KEY_MAP = {"Enter": "C-m", "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
           "Escape": "Escape", "Esc": "Escape", "C-c": "C-c", "Space": "Space", "Tab": "Tab"}

def send_key(sess, key):
    tok = KEY_MAP.get(key)
    if not tok:
        return False
    subprocess.run(["tmux", "send-keys", "-t", sess, tok], capture_output=True)
    return True

class H(BaseHTTPRequestHandler):
    def _auth(self, q):
        tok = (q.get("token", [None])[0]) or self.headers.get("X-Token")
        return tok == TOKEN

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/status":
            if not self._auth(q):
                return self._json({"error": "unauthorized"}, 401)
            return self._json(status_payload())
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._auth(q):
            return self._json({"error": "unauthorized"}, 401)
        n = int(self.headers.get("Content-Length", "0") or "0")
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            data = {}
        sess = data.get("session", "")
        if not sess:
            return self._json({"error": "missing session"}, 400)
        if u.path == "/api/send":
            ok = send_text(sess, data.get("text", ""))
            return self._json({"ok": ok})
        if u.path == "/api/key":
            ok = send_key(sess, data.get("key", ""))
            return self._json({"ok": ok})
        self._json({"error": "not found"}, 404)

PAGE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>vibe-stack</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font:14px/1.4 -apple-system,system-ui,sans-serif;background:#0d1117;color:#e6edf3}
header{padding:10px 14px;background:#161b22;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:10px;position:sticky;top:0}
header b{font-size:15px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.ok{background:#3fb950}.stale{background:#d29922}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#8b949e;margin:16px 14px 6px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;margin:8px 14px;padding:10px 12px}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.name{font-weight:600}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600}
.working{background:#163a23;color:#3fb950}.idle{background:#3a2f16;color:#d29922}.blocked{background:#4a1d1d;color:#f85149}
pre{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:8px;overflow:auto;max-height:160px;font:12px/1.35 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word;margin:8px 0}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
button,input{font:13px inherit;border-radius:7px;border:1px solid #30363d;background:#21262d;color:#e6edf3;padding:7px 10px}
button{cursor:pointer}button:active{background:#30363d}
input{flex:1;min-width:140px}
.k{padding:7px 9px}
.kan{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:0 14px 24px}
.col{background:#0f141a;border:1px solid #21262d;border-radius:10px;padding:8px;min-height:60px}
.col h3{font-size:11px;text-transform:uppercase;color:#8b949e;margin:0 0 6px}
.lane{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 8px;margin-bottom:6px;font-size:12px}
.lane .b{font-weight:600;word-break:break-all}.lane .c{color:#8b949e}
.muted{color:#8b949e;padding:0 14px}
@media(max-width:640px){.kan{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><span id="live" class="dot stale"></span><b>vibe-stack</b><span id="meta" class="muted"></span></header>
<h2>Agents</h2><div id="agents"></div>
<h2>Lanes (kanban)</h2><div id="kanban" class="kan"></div>
<script>
const TOKEN=new URLSearchParams(location.search).get("token")||"";
const COLS=[["todo","To-Do"],["in-progress","In-Progress"],["review","Review"],["done","Done"]];
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
async function api(path,method,body){
  const o={method:method||"GET",headers:{"X-Token":TOKEN}};
  if(body){o.headers["Content-Type"]="application/json";o.body=JSON.stringify(body)}
  const r=await fetch(path+"?token="+encodeURIComponent(TOKEN),o);return r.json();
}
async function send(sess){const i=document.getElementById("in-"+sess);const t=i.value;i.value="";await api("/api/send","POST",{session:sess,text:t})}
async function key(sess,k){await api("/api/key","POST",{session:sess,key:k})}
function agentCard(a){
  const keys=["Enter","Up","Down","Escape","C-c"].map(k=>`<button class=k onclick="key('${a.name}','${k}')">${k}</button>`).join("");
  return `<div class=card><div class=row><span class=name>${esc(a.name)}</span>
    <span class="badge ${a.status}">${a.status}</span>
    ${a.attached?'<span class=c style="color:#8b949e">attached</span>':''}</div>
    <pre>${esc(a.tail.join("\n"))||"(no output)"}</pre>
    <div class=ctl><input id="in-${a.name}" placeholder="message / slash cmd…"
      onkeydown="if(event.key==='Enter')send('${a.name}')">
      <button onclick="send('${a.name}')">Send</button></div>
    <div class=ctl>${keys}</div></div>`;
}
function laneCard(l){return `<div class=lane><div class=b>${esc(l.branch)}</div><div class=c>${esc(l.last_commit)}</div></div>`}
async function tick(){
  try{
    const d=await api("/api/status");
    if(d.error){document.getElementById("agents").innerHTML='<p class=muted>'+d.error+' — check token in URL</p>';return}
    document.getElementById("live").className="dot ok";
    document.getElementById("meta").textContent=new Date(d.generated_at*1000).toLocaleTimeString();
    document.getElementById("agents").innerHTML=d.agents.length?d.agents.map(agentCard).join(""):'<p class=muted>no tmux sessions</p>';
    const k=document.getElementById("kanban");k.innerHTML="";
    for(const[st,label]of COLS){
      const items=d.lanes.filter(l=>l.state===st);
      k.innerHTML+=`<div class=col><h3>${label} (${items.length})</h3>${items.map(laneCard).join("")}</div>`;
    }
  }catch(e){document.getElementById("live").className="dot stale"}
}
tick();setInterval(tick,3000);
</script></body></html>"""

if __name__ == "__main__":
    print(f"vibe-stack dashboard on :{PORT}  (repo: {REPO})")
    print(f"Open:  http://<this-host>:{PORT}/?token={TOKEN}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
