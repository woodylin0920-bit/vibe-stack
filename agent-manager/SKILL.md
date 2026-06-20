---
name: agent-manager
description: "Remote control plane for coding agents (Claude Code, Codex, OpenCode) — open an agent in a project, send tasks, drive slash commands/keys from a chat app, check status, review output, and handle per-agent auth."
version: 1.7.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Orchestration, Coding-Agent, Remote-Control, Multi-Agent, Worktree, tmux, Telegram, Automation]
    related_skills: [claude-code, codex, opencode]
---

# Agent Manager — Remote Control Plane for Coding Agents

Drive autonomous coding-agent CLIs (Claude Code, Codex, OpenCode, …) **remotely from a chat app** through an orchestrator. You message the orchestrator ("open Claude Code in the api repo", "compact the context", "switch to opus", "re-login"); the orchestrator launches, drives, monitors, and reports back on the live session.

This is the **control plane** — it coordinates agents, it does not replace the per-agent skills. For deep per-agent detail, see the sibling [`claude-code`](../claude-code/SKILL.md) skill and the upstream Codex / OpenCode docs.

> **Terminology.** *Orchestrator* = the always-on assistant the user chats with (e.g. Hermes). *Agent* = the coding CLI it launches (Claude Code / Codex / OpenCode). *Channel* = wherever the user types (Telegram, LINE, Slack, web, CLI, …) — see [Channel-agnostic](#channel-agnostic-by-design).

---

## Mental model

```
┌───────────────┐   chat msg    ┌──────────────┐   tmux send-keys   ┌─────────────┐
│  user (phone, │──────────────▶│ orchestrator │───────────────────▶│  agent CLI  │
│  web, desktop)│◀──────────────│  (Hermes)    │◀───────────────────│ (in tmux/PTY)│
└───────────────┘  status/output└──────────────┘   capture-pane     └─────────────┘
        ▲                                                                    │
        └────────────── watches the live session (e.g. claude.ai app) ──────┘
```

**Who decides:** the **user is the brain and decision-maker.** Hermes is the user's **right hand** — it aggregates, coordinates, executes, and reports back; it **surfaces options and acts on the user's choices**, it does not decide on its own. Throughout this skill, "autonomy" means *executing the user's intent*, never *replacing the user's judgment*.

**The key insight that makes this skill exist:** a user watching a session in a mobile/web app (e.g. the claude.ai app observing a `--remote-control` session) can *see* everything but **cannot inject slash commands or control keys** — there's no way to type `/compact`, `/model`, `/login`, press `Esc`, or pick a menu option from that UI. The orchestrator is the **input layer** that bridges the gap: the user expresses intent in chat, the orchestrator translates it into `tmux send-keys` against the live session.

### Channel-agnostic by design
Hermes (the orchestrator) is the layer that matters; the chat app is **just an interface**. The same workflows run over **any channel Hermes supports**:

```
User  →  [any channel: Telegram / LINE / Slack / web / CLI]  →  Hermes (orchestrator)  →  agents
```

Nothing in this skill is Telegram-specific. Wherever you read "send to the user" or "the user messages the orchestrator," it means *whichever channel they happen to be on*. Pick the channel; the playbook is unchanged.

---

## ⚠️ Prime directive — never go silent

**After dispatching any task, the orchestrator MUST NOT go silent.** Fire-and-forget is forbidden. Proactive polling is mandatory — every other section of this skill exists to serve this rule.

- **Poll after every injection.** 3–5 s after *each* `vibe send` (or raw `send-keys` / `paste-buffer`), run `vibe status` and confirm the session flipped to `working` / advanced (new output, tool activity, or a prompt). If nothing changed, the input may not have landed (e.g. a dropped Enter) — re-check and re-send.
- **Surface prompts the instant they appear — unprompted.** The moment a new prompt / selection / permission / plan-review screen shows up, *at any time* (not only right after a dispatch), push it to the user without being asked. A silent agent sitting on a dialog is a bug, not a pause.
- **Keep watching until a terminal state.** Continue monitoring (event-driven `watch_patterns` + idle fallback, see below) until the agent is unambiguously **done**, **errored**, or **waiting on the user** — then report.
- **"Dispatched" ≠ "done."** "I sent the task" is not a result. Only an *observed* outcome (files changed, tests run, commit made) counts as completion.

### Proactive status reporting (human-facing)
The human-facing half of never-go-silent — the user should **never have to ask "what's happening?"**
- **Poll periodically.** Beyond the 3–5 s post-injection check, run `vibe status` every **30–60 s** while a task runs — one call snapshots every agent session, so the whole fleet polls in a single command.
- **Report unprompted on change** — task done, blocked, decision needed, a notable milestone. Don't wait to be asked; don't narrate every line either — report *changes*, not heartbeats.
- **Consistent format**, one line per agent — `session · status · what it's doing · blocker (if any)`. Derive it straight from `vibe status`:
  ```bash
  vibe status | jq -r '.[] | "\(.session) · \(.state) · \(.lines[-1] // "—") · —"'
  ```
  ```
  claude-api · working · running auth tests (3/12) · —
  codex-omni · waiting-input · permission prompt · needs your OK to write outside the repo
  ```
- For a fleet, send a compact roll-up (one line per lane) on change; stay quiet when nothing meaningful moved.

How the rest of the skill serves this: the [chat-input pattern](#-the-remote-control--chat-input-pattern-first-class) is how you *act*, [prompt detection](#detecting-interactive-prompts-so-the-agent-doesnt-sit-silently) is how you *watch*, and the [Decision Gate](#️-decision-gate) is what you do when watching surfaces a choice.

---

## ⚠️ Drive to the goal — escalate every real decision

The twin of "never go silent." Hermes runs agents **toward the user's stated goal** and handles the mechanical path itself — but it is the user's right hand, so **every real decision goes to the user.** Autonomy here means *execution*, never *deciding*.

- **Execute from the goal, not step-by-step approval.** Given the task spec's `goal` + `done_criteria`, let the agent run the obvious loop — implement → test → fix → re-test — without asking permission for routine progress ("should I run the tests?" → just run them).
- **Self-heal the mechanical.** Recoverable issues (test failure, lint, a transient error, an idle agent mid-task) → feed back to the agent and continue. These are not decisions.
- **Escalate every real decision.** Anything irreversible, ambiguous, or a matter of taste — architecture, scope changes, delete vs keep, publish/merge, spending beyond budget, picking among option screens — **stop and ask the user** ([Decision Gate](#️-decision-gate)). The user is the brain; Hermes presents the options and acts on the choice.
- **Reconciling the principles:** *never go silent* = **visibility** (always watching; surface blockers/prompts; report outcomes). *Drive to the goal* = **execution** (keep doing the routine work without nagging). *User decides* = **authority** (real choices are always the user's). Together: **watch everything, do the routine work, surface every real decision, report the result.**

### The drive loop (`/loop` pattern)
```
while not done_criteria_met and not blocked_on_a_real_decision:
    dispatch_or_continue(agent, goal)
    sleep 3–5s; vibe status                        # never go silent
    if state == waiting-input (option/permission/plan screen):  surface_to_user → wait   # user decides
    elif recoverable_error:                feed_back(agent)         # self-heal, no ask
    elif idle_but_incomplete:              nudge(agent, "continue toward: <goal>")
report(result_to_user)
```
`/loop` inside an interactive agent can schedule this cadence within a session; otherwise the orchestrator runs the loop. Always cap iterations / budget so a stuck loop **escalates to the user** instead of spinning.

---

## ⚠️ One agent, one worktree — never share a working tree

A first-class design principle, learned the hard way: **two or more coding agents running in the same working directory clobber each other.** They check out different branches under one `.git`, `git reset`/`git checkout` yanks the tree out from under a sibling mid-edit, untracked files vanish, and "the branch HEAD moved while I was working" becomes routine. The shared filesystem is the bug — not the agents.

**The rule: every agent gets its own isolated directory via `git worktree add`. No exceptions for parallel work.**

```bash
# One worktree + branch per agent — they never touch each other's files.
git -C /repo worktree add ../lanes/feat-x -b lane/feat-x
tmux new-session -d -s claude-feat-x -x 140 -y 40
tmux send-keys -t claude-feat-x 'cd /repo/../lanes/feat-x && claude --remote-control feat-x' Enter
```

- **Each agent commits to its own `lane/<slug>` branch**, in its own worktree — never to a branch a sibling is also on. This is what makes the [lane primitive](#the-lane-primitive-first-class) safe and what keeps `main` integration the sole job of the [merge captain](#merge-captain).
- **Symptoms you skipped this:** a file you wrote is suddenly untracked or gone; `git status` shows changes you didn't make; HEAD is a different commit than a minute ago; an edit fails with "file modified since read." All of these mean another agent is sharing your tree — stop and isolate.
- **One repo, many worktrees is cheap.** `git worktree` shares the object store, so N isolated working dirs cost almost nothing. Tear each down on merge/discard: `git worktree remove <path>` + delete the branch (see [Fleet lifecycle](#fleet-lifecycle-kanban-model)).
- **The only safe shared-tree case is a single agent.** The moment work goes parallel, it goes multi-worktree. See also [pitfall #10](#pitfalls--gotchas).

---

## ★ The remote-control + chat-input pattern (first-class)

This is the headline workflow. Use it whenever the user wants to watch on one device and steer from chat.

1. **Launch** the agent in a tmux session so it has a PTY and you can inject input. Add the agent's remote-watch flag if it has one (Claude Code: `--remote-control`) so the user can follow along in the app.
   ```
   tmux new-session -d -s claude-api -x 140 -y 40
   tmux send-keys -t claude-api 'cd /path/to/api && claude --remote-control mysession' Enter
   ```
2. **User watches** in the mobile/web app; **user steers via chat** — natural-language tasks *and* the control actions the app can't perform.
3. **Orchestrator translates intent → keystrokes.** Map what the user says to what gets injected:

   | User says (chat) | Orchestrator injects |
   |------------------|----------------------|
   | "tell it to refactor the auth module" | the prompt text, then Enter |
   | "compact the context" | `/compact` + Enter |
   | "switch to opus" / "use sonnet" | `/model` + Enter, then arrow-select |
   | "clear the conversation" | `/clear` + Enter |
   | "show context usage" | `/context` + Enter |
   | "it needs to re-login" | `/login` + Enter, then surface the OAuth URL (see Auth) |
   | "stop / interrupt it" | `Escape` (or `C-c`) |
   | "pick option 2" | `Down` ×1, then Enter — **only after the Decision Gate** |

### Injecting text reliably (do this, not naive send-keys)

Sending prompt text as keystrokes is fragile — on macOS with a **CJK (Chinese/Japanese/Korean) input method active**, `tmux send-keys -t s "中文…" Enter` sends the text but **silently drops the Enter**. The robust fix is to **not send text as keystrokes at all** — inject the bytes via the paste buffer, then send Enter separately:

```
printf '%s' "中文 prompt…" | tmux load-buffer -b ag -   # stage the payload
tmux paste-buffer -t claude-api -b ag -d                # inject bytes (bypasses the IME)
tmux send-keys -t claude-api C-m                         # Enter, as its own call
```

- `paste-buffer` writes bytes straight into the pane (no keystroke simulation) → the IME can't eat anything, and multi-line / shell-special text works.
- Prefer `C-m` over the `Enter` token (literal carriage return, less ambiguous), **always as a separate call**.
- If you must use `send-keys` for text, use `send-keys -l -- "text"` (literal) so key-names inside the text aren't interpreted, then send `C-m` separately.
- Pure-ASCII prompts are safe in one `send-keys … Enter` call, but the paste-buffer method is the safe default for anything user-supplied.

---

## Core operations (verb vocabulary)

What the user asks for, and how the orchestrator does it. Hermes drives these through the **`vibe` CLI** (`bin/vibe`) — a thin shell wrapper over the raw tmux mechanics, so the orchestrator calls one stable verb instead of hand-assembling `paste-buffer`/`capture-pane` each time. The right column shows the underlying tmux that `vibe` runs — reach for it directly only when you need something `vibe` doesn't wrap (e.g. control keys, arrow-select).

| Verb | What it means | `vibe` command | Underlying tmux |
|------|---------------|----------------|-----------------|
| **open** | start an agent in a project | `vibe new <agent> <session> <workdir> "<task>"` | `tmux new-session` → launch cmd (cd + agent) |
| **task** | give it work | `vibe send <session> "<prompt>"` | paste-buffer + `C-m` (CJK-safe) |
| **status** | is it working / waiting / done? | `vibe status` → JSON per session (`state`, `lines`) | `capture-pane -p -S -` (+ `watch_patterns`) |
| **review** | see the output | `vibe status` (read `.lines`) or tail the pane | `capture-pane -p -S -`; or `--output-format json` |
| **control** | slash command / control key | `vibe send <session> "/compact"`; control keys → raw | `send-keys` of the slash command or key |
| **list** | what's running? | `vibe status` (one call lists every agent session) | `tmux ls` |
| **stop** | end / clean up | `vibe kill <session>` | per-agent exit (below) + `tmux kill-session -t <name>` |

> `vibe status` is the polling primitive: one call returns **every** coding-agent session with its detected `state` (`idle` / `working` / `waiting-input`) and last 3 output lines — exactly what the never-go-silent loop and the human-facing roll-up below consume. Install it once (see the repo README); it shells out to the same tmux calls documented here.

---

## Detecting interactive prompts (so the agent doesn't sit silently)

Agents pause on plan-review screens, permission dialogs, and menu choices. A fixed `sleep` + one capture misses these. Use a **two-tier detector**:

- **Event-driven (primary):** register `watch_patterns` on the launched process for known dialog signatures so the orchestrator wakes the instant one appears. Keep a small per-agent catalog — they're stable strings:
  `"❯ 1."`, `"Do you want"`, `"trust this folder"`, `"Yes, I accept"`, `"(y/n)"`, `"Esc to interrupt"`, `"/login"`, `"No, exit"`.
- **Idle fallback (catches unknown prompts):** poll `tmux capture-pane -p -S -` every ~10–15 s; if the pane is **unchanged for ~20–30 s** *and* the last non-empty line looks like an input/selection row (`❯`, `│ >`, `1.` / `2.`), treat it as "waiting" even with no signature match.

On a hit → `capture-pane` the dialog, push it to the user via the chat layer, **wait for the answer (Decision Gate)**, then inject the choice. Normalize whitespace before matching; `capture-pane -p` already strips ANSI.

---

## Per-agent playbooks

Each agent follows the same template: **Launch · Auth · Drive · Status · Stop**.

### Claude Code  ·  see [`claude-code`](../claude-code/SKILL.md) for depth
- **Launch:** `claude` (interactive) · `claude -p 'task'` (one-shot) · `claude --remote-control <name>` (watchable session). Needs a PTY for interactive use → run inside tmux.
- **Auth:** `claude auth login` — subscription OAuth (default), `--console` (API billing), `--sso` (Enterprise). Check with `claude auth status`. **Remote re-auth:** inject `/login`, read the pane for the `https://…/authorize` URL, send that link to the user to approve from their device; the session finishes the callback automatically.
- **Drive:** `send-keys` prompts + slash commands (`/compact`, `/model`, `/context`, `/clear`). Two startup dialogs: workspace-trust (Enter = accept) and, with `--dangerously-skip-permissions`, the bypass warning (**Down then Enter**).
- **Status:** `capture-pane`; `❯` = waiting; for `--remote-control`, confirm `/rc active` in the status bar.
- **Stop:** `/exit` (or `C-d`), then `tmux kill-session`.

### Codex
- **Launch:** `codex` (interactive TUI) · `codex exec 'task'` (one-shot). **Always `pty=true`** — hangs without a PTY. **Must run inside a git repository.** Auto-approval: `--full-auto` (sandboxed) or `--yolo` (no sandbox — dangerous).
- **Auth:** `OPENAI_API_KEY`, **or** Codex CLI OAuth (creds at `~/.codex/auth.json`). A missing `OPENAI_API_KEY` alone does *not* mean auth is absent — check for the OAuth session too.
- **Drive:** one-shot via `codex exec`; interactive via tmux `send-keys`, or background-PTY via `process(action="submit", data="…")`.
- **Status:** `process(action="poll"/"log", session_id=…)`, or `capture-pane` under tmux.
- **Stop:** `process(action="kill")`, or `C-c` under tmux.

### OpenCode
- **Launch:** `opencode run 'task'` (bounded one-shot, **no PTY needed**) · `opencode` (interactive TUI — `background=true, pty=true`). Resume: `opencode -c` (last) / `opencode -s <id>` (specific).
- **Auth:** `opencode auth login`, or set a provider key (e.g. `OPENROUTER_API_KEY`). Verify with `opencode auth list` (should show ≥1 provider).
- **Drive:** `process(action="submit", data="…")` for follow-ups; in the TUI, `Ctrl+X M` switches model, `Ctrl+X L` switches session.
- **Status:** `process(action="poll"/"log")`, or `capture-pane`.
- **Stop:** **`Ctrl+C` (`\x03`) — NOT `/exit`** (`/exit` opens an agent-selector dialog). Or `process(action="kill")`.

### Adding a new agent (checklist)
For any agent not listed, capture five facts before driving it remotely:
1. **Launch** command (interactive vs one-shot/`exec`/`run`).
2. **PTY required?** (most TUIs hang without one).
3. **Auth** method + where credentials live + how to re-auth remotely.
4. **Status** method (`capture-pane` signatures vs `process poll`).
5. **Exit** method (`/exit`? `Ctrl+C`? `kill`?) — get this wrong and sessions leak or hang.

---

## Auth / login matrix

| Agent | Auth method | Credentials live in | Remote re-auth |
|-------|-------------|---------------------|----------------|
| Claude Code | Subscription OAuth · `--console` API · `--sso` | OAuth keychain / `ANTHROPIC_API_KEY` | inject `/login` → send OAuth URL to user → user approves on device |
| Codex | `OPENAI_API_KEY` · Codex OAuth | env / `~/.codex/auth.json` | run login flow, surface any device/OAuth URL to the user |
| OpenCode | `opencode auth login` · provider key | provider config / `OPENROUTER_API_KEY` etc. | run `opencode auth login`, relay any URL/code to the user |

**Generalized remote re-auth flow:** trigger the agent's login → capture the URL/code from the pane → send it to the user via the chat layer → the user approves on their own device → verify (`… auth status` / `auth list`) and resume. The orchestrator should **not** click "Authorize" itself unless the user explicitly asks.

---

## Status & lifecycle

- **Naming:** one session per agent+project, named `<agent>-<project>` (e.g. `claude-api`, `codex-omni`). Predictable names make `capture-pane` / `kill-session` unambiguous.
- **Before opening a new session:** run `tmux ls` and tell the user what's already running (avoid duplicates).
- **Cleanup:** `tmux kill-session -t <name>` when done; background sessions persist otherwise.
- **Don't kill slow sessions** — an agent may be mid multi-step work. Check progress with `capture-pane` first.

---

## Model routing — match the model to the job

Route deliberately; different stages want different models.

| Stage | Model | Why |
|-------|-------|-----|
| Planning · brainstorming · synthesis · hard review | **Opus 4.8** (`--model opus`, `--effort high`/`max`) | deepest reasoning — worth the cost on the thinking that steers everything else |
| Implementation · refactors · most coding | **Sonnet** (`--model sonnet`) or **GPT-5.5** (Codex) | strong, fast, cost-effective for well-scoped work |
| Quick / mechanical (rename, format, one-liners, status) | **Haiku** (`--model haiku`, `--effort low`) | cheapest + fastest; reasoning isn't the bottleneck |

- Spend the big model where a wrong call is expensive (architecture, the task spec itself, merge review, brainstorm synthesis); implement with the mid tier; escalate a stuck lane to Opus.
- In [race mode](#race-mode), vary models **on purpose** (Opus vs Sonnet vs GPT-5.5) for genuinely diverse attempts.
- Set it per lane via the task spec's `model:` field; override at launch with `--model` / `--effort` (Claude Code) or `--model` (Codex / OpenCode).

---

## Multi-agent orchestration (fleets)

Everything above drives **one** agent. To "spawn agents, assign tasks, review output, merge work" you scale to a **fleet** — many agents working in parallel, each isolated, with a disciplined path to `main`. The unit of work is the **lane**.

### The lane primitive (first-class)

A **lane** is one unit of parallel work = **worktree + branch + agent session + status log**. All four share one slug so they're trivially linkable:

| Component | What | Example (slug `feat-x`) |
|-----------|------|-------------------------|
| **worktree** | isolated `git worktree` so agents never collide on the working tree | `../lanes/feat-x` |
| **branch** | dedicated branch; agents commit here, **never to main** | `lane/feat-x` |
| **agent session** | the tmux/PTY session driving the agent in that worktree | `claude-feat-x` |
| **status log** | append-only file: state, last poll, prompts surfaced, result | `.lanes/feat-x.md` |

Open a lane:
```
git -C /repo worktree add ../lanes/feat-x -b lane/feat-x
tmux new-session -d -s claude-feat-x -x 140 -y 40
tmux send-keys -t claude-feat-x 'cd /repo/../lanes/feat-x && claude --remote-control feat-x' Enter
# then inject the task spec as the first task; poll per the Prime directive
```
The [Prime directive](#️-prime-directive--never-go-silent) applies **per lane** — poll each one, surface each one's prompts.

### Task spec (the work order)

Every lane starts from a **task spec** — a small markdown/YAML doc that is the contract the agent builds to and reviewers check against:
```yaml
goal: <one sentence — what success looks like>
model: <opus | sonnet | gpt-5.5 | haiku — see Model routing; pick for the work's hardest step>
constraints: [<rules the agent must respect, e.g. "no new deps", "keep API stable">]
target_files: [<paths likely to change>]
test_command: <how to verify, e.g. "npm test">
done_criteria: [<observable conditions: tests green, lints clean, feature reachable>]
```
Inject the spec as the agent's first task. The review gate and merge captain judge work against `done_criteria` + `test_command` — not vibes.

### Right-size the work order — max 3 deliverables per agent

**Cap each agent at 3 deliverables per task. Need more? Fan out parallel agents (one lane each), don't pile them on one agent.**

A single agent handed a long backlog goes slow and unfocused — it loses the thread between unrelated items, half-finishes several, and gives you no clean review surface. Three is the ceiling where one agent still holds the whole task in working memory and produces a tight, reviewable diff.

- **Splitting up?** Carve the backlog into independent chunks of ≤3 deliverables and open a [lane](#the-lane-primitive-first-class) per chunk — they run concurrently and each lands as its own reviewable branch.
- **Truly sequential** (item N depends on N−1)? Keep one lane but feed the deliverables in waves of ≤3, polling each wave to a terminal state before injecting the next.
- **Each deliverable = one commit** so the review gate stays granular.

> Lesson learned the hard way: one agent given 14 tasks crawled and lost focus; the same 14 split across parallel lanes of ≤3 finished faster and reviewed cleanly.

### Race mode

Run the **same task spec across multiple agents/worktrees**, then keep the best result:
1. **Fan out** N lanes from one spec — vary the agent or model (Claude vs Codex vs OpenCode; opus vs sonnet) to get genuinely different attempts.
2. Each lane produces a diff on its own branch.
3. **Compare:** `git diff main...lane/<slug>` per lane; run the spec's `test_command` in each; score against `done_criteria`.
4. **Keep the winner** (merge its branch via the gate below); discard the rest (`git worktree remove` + delete branch + kill session).

Use when the approach is uncertain and you'd rather pick from several attempts than iterate one.

### Review gate (before any merge)

No lane reaches `main` without passing the gate — surface the result to the user; **on the user's approval**, the merge captain integrates:
1. **Diff** — `git diff main...lane/<slug>`; scope check: did it touch only the expected `target_files`?
2. **Tests** — run `test_command`; must pass.
3. **Reviewer agent (optional)** — a *separate* agent reviews the diff against the spec for correctness, security, and scope creep, e.g. `claude -p 'Review this diff against the task spec. Flag bugs, security, and scope creep.' --max-turns 1`.

### Merge captain

A single **integration role** owns `main`. **Agents never self-merge `main`.**
- Agents commit only to their `lane/<slug>` branch.
- The merge captain (a dedicated role/agent, or the orchestrator acting as integrator) is the **only** one that merges gate-passing lanes into `main` — **on the user's go-ahead**, **one at a time**, re-running `test_command` after each integration to catch cross-lane conflicts before the next merge.
- This serializes integration, keeps `main` always-green, and prevents racey concurrent merges.

### Fleet lifecycle (Kanban model)

Track lanes on a board: **spec → in-progress → in-review → merged / discarded**. On merge or discard, tear the lane down: `git worktree remove <path>`, delete the branch, `tmux kill-session`, archive the status log.

### Prior art
- **[claude-squad](https://github.com/smtg-ai/claude-squad)** — terminal orchestrator that manages multiple agents (Claude Code, Codex, OpenCode, Amp) with **tmux + git-worktree** isolation; the lane/session model here mirrors it.
- **[vibe-kanban](https://github.com/BloopAI/vibe-kanban)** — a **Kanban board** where each task card provisions a branch + workspace and flows To-Do → In-Progress → Review → Done with one-click PRs; the task-spec → lane → gate → merge flow here is the same shape.

---

## Ecosystem integrations

vibe-stack **composes; it doesn't reimplement** what others already built well. Inside the fleet/lane model, reach for:

- **Claude → Codex delegation — use [codex-orchestrator](https://github.com/kingbootoshi/codex-orchestrator).** When the pattern is "Claude Code plans/synthesizes, Codex does the deep implementation," don't hand-roll it: run codex-orchestrator (it delegates tasks to Codex via tmux, *designed for* Claude Code orchestration) **inside a lane**. Claude stays the planner; Codex does the coding; vibe-stack carries the whole thing over chat to the user.
- **Visual TUI / dashboard alongside chat** — [Agent of Empires](https://github.com/agent-of-empires/agent-of-empires) or [claude-squad](https://github.com/smtg-ai/claude-squad) can watch the same tmux sessions you drive; TUI at the desk, chat on the phone.
- **Turnkey supervised team** — [Batty](https://github.com/battysh/batty) if you want a binary daemon for unattended, test-gated team runs instead of the skill-expressed fleet here.

Full landscape + when-to-use each: [docs/ecosystem.md](../docs/ecosystem.md).

---

## Rules — human-in-the-loop

### ⚠️ Never go silent (prime directive)
After dispatching any task, keep the user informed: `capture-pane` 3–5 s after every injection to confirm progress, surface any new prompt the instant it appears (unprompted), and report the observed outcome — not just "dispatched". Fire-and-forget is forbidden. Full rule: [Prime directive](#️-prime-directive--never-go-silent).

### ⚠️ Decision Gate
When an agent presents **options / choices** (numbered list, yes/no, proceed/abort, plan-review), **stop and ask the user** which to pick before injecting any key. Do NOT auto-select, press Enter, or choose on their behalf.
1. `capture-pane` the current state.
2. Send it to the user via the chat layer.
3. Wait for their explicit answer.
4. Only then inject the choice.

**Safe to auto-confirm without asking:** workspace-trust ("Yes, I trust this folder") and the `--dangerously-skip-permissions` acceptance (Down + Enter). Everything else — architecture choices, which file to modify, delete vs keep, publish vs skip — **ask first**.

### Reporting back
After a task finishes, summarize to the user what changed (files, commits, test results) — don't just say "done".

---

## Pitfalls & Gotchas

1. **Mobile/web agent UIs can't inject slash commands or control keys** — the whole reason this skill exists. Watching ≠ steering; the orchestrator must `send-keys`.
2. **CJK `send-keys` + Enter in one call drops the Enter** (macOS, IME active) — use the paste-buffer method, send `C-m` as a separate call.
3. **PTY is mandatory for interactive agents** — Codex and OpenCode TUIs (and `claude` interactive) hang without `pty=true` / a tmux PTY.
4. **OpenCode exits on `Ctrl+C`, never `/exit`** — `/exit` opens an agent-selector dialog instead.
5. **Codex must run inside a git repo** — it refuses otherwise.
6. **Remote re-auth needs the URL surfaced** — capture it from the pane and send it to the user; don't click Authorize yourself.
7. **Going silent after dispatch** — the cardinal sin (see [Prime directive](#️-prime-directive--never-go-silent)). An agent stuck on a dialog looks like it's "still working"; without proactive polling + prompt detection you'll never notice. Poll after every injection; surface prompts unprompted.
8. **Clean up tmux sessions** — `tmux kill-session` when done, or they leak. For fleets, also `git worktree remove` + delete the branch, or worktrees pile up.
9. **Agents self-merging `main`** — forbidden. Agents commit only to `lane/<slug>`; only the [merge captain](#merge-captain) integrates, one lane at a time with tests re-run. Concurrent self-merges corrupt `main`.
10. **Parallel agents without worktree isolation** — multiple agents in the same working tree clobber each other. One [lane](#the-lane-primitive-first-class) = one `git worktree`, always.
11. **Overloading one agent with a long backlog** — more than ~3 deliverables and a single agent slows down and loses focus. Cap at 3 per agent; for more, [fan out parallel lanes](#right-size-the-work-order--max-3-deliverables-per-agent).
