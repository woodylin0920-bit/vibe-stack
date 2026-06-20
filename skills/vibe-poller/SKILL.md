---
name: vibe-poller
description: "Cron-style status poller — Hermes runs `vibe status` every 60s and Telegrams the user the moment an agent changes state (idle↔working↔waiting-input), including the last output lines when a task finishes."
version: 1.0.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Monitoring, Poller, Cron, Telegram, Visibility, Automation]
    related_skills: [agent-manager, overnight]
---

# vibe-poller — never wonder what your agents are doing

This skill turns Hermes into a watchdog for your coding agents: it polls `vibe status` on a fixed cadence and **proactively messages you the instant anything changes** — so you never have to ask "what's happening?". It is the always-on, human-facing arm of the agent-manager [Prime directive](../../agent-manager/SKILL.md).

## Prerequisites
- `vibe` on `PATH` (the [vibe-stack CLI](../../bin/vibe)). `vibe status` returns JSON; `vibe logs <session> --tail N` returns clean output lines.
- Hermes with a Telegram (or any) channel configured.

## Schedule it on Hermes's native cron (don't reinvent scheduling)
Hermes already has a cron subsystem — use it. Register a job that fires this poll every 60 seconds; the job body is "run the vibe-poller check and message me on any change." (`hermes cron` / the Cron page; see Hermes docs.) Inside a single interactive session you can instead use `/loop 60s`. Either way the cadence is **60s**.

## What the poll does each tick
1. Run `vibe status` (JSON: one object per agent session with `session`, `state`, `agent`, `lines`).
2. Compare each session's `state` to the **last seen** state (persisted in `~/.vibe-stack/poller-state.tsv`).
3. For every session whose state **changed** (`idle→working`, `working→idle`, `*→waiting-input`, `working→…`, new session, or a session that disappeared) → send the user one Telegram message.
4. When a session goes **working → idle** (a task likely just finished), capture `vibe logs <session> --tail 10` and include those lines in the message.
5. Save the new states back to the state file. Stay silent when nothing changed.

## Message format
`<emoji> <session> — <what happened>` then, when relevant, the last output:
```
🟢 claude-api — finished (working → idle)
   last 10 lines:
   > all tests passing (12/12)
   > committed: add JWT refresh
   …
🟡 codex-omni — needs you (waiting-input)
🔵 claude-web — started working (idle → working)
🔴 claude-old — session ended
```
Emoji follow `vibe`'s convention: 🟢 idle · 🔵 working · 🟡 waiting-input · 🔴 gone/unknown.

## Reference poll (Hermes runs this; it prints change-events to relay)
Pure shell, bash 3.2, deps: `vibe`, `python3` (already used in the repo) for JSON parsing. Prints one line per change; emits nothing when quiet. Hermes relays each line (and any captured logs) to the channel.

```bash
#!/usr/bin/env bash
set -u
STATE="${VIBE_STATE_DIR:-$HOME/.vibe-stack}/poller-state.tsv"
mkdir -p "$(dirname "$STATE")"; [ -f "$STATE" ] || : > "$STATE"
prev_state() { awk -F'\t' -v s="$1" '$1==s{print $2; exit}' "$STATE"; }

now=$(mktemp); vibe status \
  | python3 -c 'import sys,json
for a in json.load(sys.stdin): print(a["session"]+"\t"+a["state"])' > "$now" 2>/dev/null

emoji() { case "$1" in idle) printf 🟢;; working) printf 🔵;; waiting-input) printf 🟡;; *) printf 🔴;; esac; }

# transitions for current sessions
while IFS=$'\t' read -r s st; do
  [ -n "$s" ] || continue
  was=$(prev_state "$s")
  [ "$was" = "$st" ] && continue
  case "$st" in
    working)       printf '%s %s — started working (%s → working)\n' "$(emoji "$st")" "$s" "${was:-new}";;
    waiting-input) printf '%s %s — needs you (waiting-input)\n' "$(emoji "$st")" "$s";;
    idle)          printf '%s %s — finished (%s → idle)\n' "$(emoji "$st")" "$s" "${was:-?}"
                   if [ "$was" = "working" ]; then echo "   last 10 lines:"; vibe logs "$s" --tail 10 | sed 's/^/   > /'; fi;;
    *)             printf '%s %s — %s\n' "$(emoji "$st")" "$s" "$st";;
  esac
done < "$now"

# sessions that disappeared
while IFS=$'\t' read -r s st; do
  [ -n "$s" ] || continue
  grep -q "^$s	" "$now" || printf '🔴 %s — session ended\n' "$s"
done < "$STATE"

mv "$now" "$STATE"
```

## Rules (inherited from agent-manager)
- **Report changes, not heartbeats** — silent when nothing moved (this skill is *event* notifications; for periodic "still alive" pings use the [overnight](../overnight/SKILL.md) heartbeat).
- **Surface `waiting-input` immediately** — that's the user's cue to decide (the [Decision Gate](../../agent-manager/SKILL.md)).
- **The user decides; Hermes reports.** The poller never acts on a state change beyond notifying.
