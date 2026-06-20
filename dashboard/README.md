# vibe-stack dashboard

A minimal, real-time web view **and** control surface for your tmux coding agents — open it from your phone. Single file, **Python stdlib only** (no deps, no build).

Shows:
- **Agents** — every tmux session, a status badge (**working / idle / blocked**), and the last lines of output.
- **Controls** (per agent) — a message/slash-command box plus quick keys (Enter, ↑, ↓, Esc, Ctrl-C). Text is injected with the **CJK-safe paste-buffer method** (`load-buffer` → `paste-buffer` → `C-m`).
- **Lanes (kanban)** — derived from `git` worktrees + `lane/*` / `feature/*` branches, bucketed into To-Do / In-Progress / Review / Done.

## Run

```bash
python3 dashboard/server.py
# → prints:  Open: http://<this-host>:8765/?token=<TOKEN>
```

Open that URL on your phone. The `token` in the URL authenticates you — **all** API calls (status + control) require it.

### Config (env vars)
| Var | Default | Purpose |
|-----|---------|---------|
| `PORT` | `8765` | listen port |
| `VIBE_REPO` | `~/projects/repo/vibe-stack` | repo to derive lanes from |
| `VIBE_TOKEN` | generated → `~/.hermes/dashboard.token` (chmod 600) | auth token |

## Access from your phone

- **Same WiFi (LAN):** `http://<mac-lan-ip>:8765/?token=…` (e.g. `http://192.168.0.100:8765/…`).
- **From anywhere (Tailscale):** install Tailscale on the host and phone; use the host's Tailscale IP/name in the URL. The server binds `0.0.0.0`, so it's reachable over whatever network you put it on.

## Status heuristic
- **blocked** — a prompt/selection signature is on screen (`❯ 1.`, "Do you want", `(y/n)`, "Yes, I accept", `/login`, …).
- **working** — activity markers (`Esc to interrupt`, spinner glyphs, token counters) or the pane changed since the last poll.
- **idle** — a ready prompt with no activity.

## Security notes
- The token gates everything; treat the URL like a password.
- Binding `0.0.0.0` exposes it to your whole network — keep it on a trusted LAN or Tailscale, **not** a public tunnel without an extra layer.
- Control endpoints inject keystrokes into live agent sessions; anyone with the token can drive them.
