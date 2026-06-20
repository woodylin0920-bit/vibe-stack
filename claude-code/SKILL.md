---
name: claude-code
description: "Drive the Claude Code CLI from an orchestrator — pick print vs interactive mode, orchestrate via tmux, handle dialogs/auth, and follow human-in-the-loop rules."
version: 3.0.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Claude, Anthropic, Code-Review, Refactoring, PTY, Automation]
    related_skills: [codex, hermes-agent, opencode]
---

# Claude Code — Orchestration Guide

Delegate coding to [Claude Code](https://code.claude.com/docs/en/cli-reference) (Anthropic's autonomous coding-agent CLI) from an orchestrator (e.g. Hermes). Claude Code can read/write files, run shell commands, spawn subagents, and manage git autonomously.

This is the general playbook: TL;DR → modes → reference → patterns → rules → pitfalls.

---

## TL;DR — pick a mode, run it

| Situation | Mode | One-liner |
|-----------|------|-----------|
| One-shot task (fix/feature/refactor/review), no follow-up | **Print (`-p`)** | `claude -p 'task' --allowedTools 'Read,Edit' --max-turns 10` |
| Multi-turn work an agent drives in the background | **tmux interactive** | `tmux new-session -d -s claude-x …` then `send-keys` / `capture-pane` |
| Session a human watches/types on their desktop | **Terminal REPL** | launch `claude` directly in a terminal window |

**Defaults that save grief:** always set `workdir`; set `--max-turns` in print mode; restrict with `--allowedTools`; clean up tmux sessions when done.

```bash
# The 90% case — non-interactive, scoped, bounded
claude -p 'Add error handling to all API calls in src/' --allowedTools 'Read,Edit' --max-turns 10
```

---

## Two Modes

### Mode 1 — Print mode (`-p`): non-interactive (PREFERRED)

Runs one task, returns the result, exits. No PTY, no dialogs, no interactive prompts — ideal for automation.

```
terminal(command="claude -p 'Add error handling to all API calls in src/' --allowedTools 'Read,Edit' --max-turns 10", workdir="/path/to/project", timeout=120)
```

Use it for: one-shot coding tasks, CI/scripting, structured extraction (`--json-schema`), piped input (`cat file | claude -p '…'`), anything without multi-turn conversation. **Print mode skips ALL dialogs** (trust + permissions).

### Mode 2 — Interactive PTY via tmux: multi-turn

A full conversational REPL where you send follow-ups, use slash commands, and watch progress. **Requires tmux** for `send-keys` (input) + `capture-pane` (monitoring).

```
# 1. start session
terminal(command="tmux new-session -d -s claude-work -x 140 -y 40")
# 2. launch Claude inside it
terminal(command="tmux send-keys -t claude-work 'cd /path/to/project && claude' Enter")
# 3. wait for welcome screen, handle dialogs (see below), then send the task
terminal(command="sleep 5 && tmux send-keys -t claude-work 'Refactor the auth module to use JWT' Enter")
# 4. monitor
terminal(command="sleep 15 && tmux capture-pane -t claude-work -p -S -50")
# 5. follow-up / exit
terminal(command="tmux send-keys -t claude-work '/exit' Enter")
```

Use it for: iterative refactor→review→fix→test cycles, human-in-the-loop decisions, exploratory sessions, slash commands (`/compact`, `/review`, `/model`).

> ⚠️ **CJK + Enter in one call drops the Enter.** With a Chinese/Japanese/Korean input method active on macOS, `tmux send-keys -t s "中文…" Enter` sends the text but silently drops Enter. **Always split:** `tmux send-keys -t s "text"` then `tmux send-keys -t s "" Enter`. English-only prompts are safe in one call. (See Pitfalls.)

### Dialog handling (interactive only)

Claude Code shows up to two confirmation dialogs. Handle via `send-keys`:

**Dialog 1 — Workspace Trust** (first visit to a directory; appears once, then cached):
```
❯ 1. Yes, I trust this folder   ← DEFAULT — just press Enter
  2. No, exit
```
→ `tmux send-keys -t <session> Enter`

**Dialog 2 — Bypass Permissions** (only with `--dangerously-skip-permissions`; recurs each launch):
```
  1. No, exit                   ← DEFAULT (WRONG)
❯ 2. Yes, I accept
```
→ must go DOWN first: `tmux send-keys -t <session> Down && sleep 0.3 && tmux send-keys -t <session> Enter`

### Decision: print vs interactive
- **Print** when the task is self-contained and you want structured output / no dialog handling.
- **Interactive (tmux)** when you need follow-ups, slash commands, or to react to what Claude asks.

---

## Essential Reference (commonly used)

> Full flag/command/shortcut lists: see the [official CLI reference](https://code.claude.com/docs/en/cli-reference). Below is only what an orchestrator typically uses.

### Subcommands
| Subcommand | Purpose |
|------------|---------|
| `claude` | Start interactive REPL |
| `claude "query"` | REPL with an initial prompt |
| `claude -p "query"` | Print mode (non-interactive, exits when done) |
| `cat file \| claude -p "query"` | Pipe content as stdin context |
| `claude -c` | Continue the most recent conversation in this directory |
| `claude -r "id"` | Resume a session by ID/name |
| `claude auth login` / `auth status` | Sign in (`--console` API billing, `--sso` Enterprise) / check login |
| `claude mcp add\|list\|remove` | Manage MCP servers |
| `claude doctor` | Health check (install + auto-updater) |
| `claude update` | Update to latest |

### Flags worth remembering
**Session/env:** `-p` (print) · `-c` (continue) · `-r <id>` (resume) · `--fork-session` · `--add-dir <paths>` · `-w, --worktree [name]` (isolated git worktree) · `--no-session-persistence` (CI).

**Model/perf:** `--model sonnet|opus|haiku` · `--effort low|medium|high|max|auto` · `--max-turns <n>` (print only) · `--max-budget-usd <n>` (print only, min ~$0.05) · `--fallback-model haiku` (print only, handles overload).

**Permissions:** `--dangerously-skip-permissions` (auto-approve all) · `--permission-mode default|acceptEdits|plan|auto|dontAsk|bypassPermissions` · `--allowedTools '…'` / `--disallowedTools '…'`.

**Output/context:** `--output-format text|json|stream-json` · `--json-schema '<schema>'` · `--verbose` · `--append-system-prompt '<text>'` (adds to, doesn't replace) · `--bare` (skip hooks/plugins/MCP/CLAUDE.md/OAuth — fastest, needs `ANTHROPIC_API_KEY`).

**Tool-name syntax** (for `--allowedTools`): `Read` · `Edit` · `Write` · `Bash` · `Bash(git *)` · `Bash(npm run lint:*)` · `WebSearch` · `WebFetch` · `mcp__<server>__<tool>`.

### Slash commands (interactive)
`/compact [focus]` (compress context; CLAUDE.md survives) · `/clear` · `/context` (usage grid) · `/cost` · `/resume` · `/review` · `/security-review` · `/model` · `/effort` · `/login` · `/exit` (or Ctrl+D).

### Settings & memory hierarchy
- **Settings** (high→low): CLI flags → `.claude/settings.local.json` (personal, gitignored) → `.claude/settings.json` (team) → `~/.claude/settings.json` (global).
- **Memory (CLAUDE.md):** `~/.claude/CLAUDE.md` (global) → `./CLAUDE.md` (project) → `.claude/CLAUDE.local.md` (personal). In interactive mode, `#` prefix quick-adds a memory line.

---

## Orchestration Patterns

### PR / diff review
```
# quick (print)
terminal(command="cd /repo && git diff main...feature | claude -p 'Review this diff for bugs, security, style. Be thorough.' --max-turns 1", timeout=60)
# from a PR number
terminal(command="claude -p 'Review this PR thoroughly' --from-pr 42 --max-turns 10", workdir="/repo", timeout=120)
```

### Structured JSON output
```
terminal(command="claude -p 'Analyze auth.py for security issues' --output-format json --max-turns 5", workdir="/project", timeout=120)
```
Key result fields: `result`, `session_id` (resume), `num_turns`, `total_cost_usd`, `subtype` (`success` / `error_max_turns` / `error_budget`). For schema-validated extraction add `--json-schema '<schema>'` and enough `--max-turns` (Claude must read files first).

### Session continuation
```
# resume by id (capture session_id from a prior --output-format json run)
terminal(command="claude -p 'Continue and add connection pooling' --resume <id> --max-turns 5", workdir="/project")
# or most recent in this directory
terminal(command="claude -p 'What did you do last time?' --continue --max-turns 1", workdir="/project")
```

### Monitor a tmux session until done (canonical loop)
```
# poll the pane; '❯' at the bottom = waiting for input (done or asking)
terminal(command="sleep 20 && tmux capture-pane -t claude-work -p -S -40")
```
Reading the TUI: `❯` = waiting for input · `●` lines = actively using tools · `⏵⏵ bypass permissions on` = perms mode · don't kill a slow session — it may be mid multi-step work; check progress instead.

### Parallel instances
Run independent tasks in separate tmux sessions (name `claude-<project>`), then sweep:
```
terminal(command="tmux new-session -d -s task1 -x 140 -y 40 && tmux send-keys -t task1 'cd ~/proj && claude -p \"fix auth bug\" --allowedTools \"Read,Edit\" --max-turns 10' Enter")
terminal(command="sleep 30 && for s in task1 task2; do echo \"== $s ==\"; tmux capture-pane -t $s -p -S -5; done")
```

### Context essentials (trim — see docs for depth)
- **CLAUDE.md** auto-loads from project root; be specific ("2-space indent for JS", not "write good code"). Many rules → split into `.claude/rules/*.md`.
- **Subagents** in `.claude/agents/*.md` (frontmatter: `name`, `description`, `model`, `tools`), invoke with `@name`. Or pass `--agents '<json>'` per session.
- **Hooks** in `.claude/settings.json` — 8 events (`PreToolUse` exit 2 = block, `PostToolUse` auto-format, `Stop`, `SessionStart`, …). Env: `CLAUDE_PROJECT_DIR`, `CLAUDE_FILE_PATHS`, `CLAUDE_TOOL_INPUT`.
- **MCP** — `claude mcp add -s user|local|project <name> -- <cmd>`; in CI use `--mcp-config <file> --strict-mcp-config`; cap output with `MAX_MCP_OUTPUT_TOKENS`.

### Cost & performance
`--max-turns` (start 5–10) · `--effort low` for simple tasks · `--bare` for CI · `--allowedTools` to minimum · `--model haiku` cheap / `opus` complex · `--fallback-model haiku` for overload · `/compact` when context >70% · start fresh sessions per distinct task.

---

## Rules for Orchestrating Agents

### ⚠️ Decision Gate — ask the user before acting on choices
When Claude Code finishes planning and presents **options / choices** (numbered list, yes/no, proceed/abort), the orchestrator should **stop and ask the user** which to pick before sending any key. Do NOT auto-select, press Enter, or choose on their behalf.
1. `tmux capture-pane` — grab the current TUI state
2. Share the captured text with the user
3. Wait for their explicit answer
4. Only then `tmux send-keys` to execute the choice

**Safe to auto-confirm without asking:** the workspace-trust dialog ("Yes, I trust this folder") and the `--dangerously-skip-permissions` acceptance (Down + Enter). Everything else (architecture choice, which file to modify, delete vs keep, publish vs skip) → **ask first**.

### Operating rules
1. Prefer print mode (`-p`) for single tasks — cleaner, no dialogs, structured output.
2. Use tmux for multi-turn interactive work — the only reliable way to orchestrate the TUI.
3. Always set `workdir` — keep Claude focused on the right project.
4. Set `--max-turns` in print mode — prevents runaway loops and cost.
5. Monitor with `tmux capture-pane -t <session> -p -S -50`.
6. Look for `❯` — Claude is waiting for input (done or asking).
7. Clean up tmux sessions when done (`tmux kill-session -t <name>`).
8. Report results to the user — summarize what changed.
9. Don't kill slow sessions — check progress first.
10. Use `--allowedTools` to restrict to what the task needs.

---

## Pitfalls & Gotchas

1. **`claude -p` default timeout is 60s in `terminal()`** — set `timeout=120`+ for longer tasks; for simple script execution, write+run the script directly (`/usr/bin/python3 /tmp/x.py`) rather than delegating to the CLI.
2. **Interactive mode requires tmux** — `pty=true` alone works but tmux gives `capture-pane`/`send-keys`, essential for orchestration.
3. **`--remote-control` requires `background=True` + `pty=True`** — without `pty`, Claude exits with the stdin error. Both flags required.
4. **`--dangerously-skip-permissions` dialog defaults to "No, exit"** — send Down then Enter to accept. Print mode skips it entirely.
5. **`--max-budget-usd` minimum ~$0.05** — system-prompt cache creation alone costs this; lower errors immediately.
6. **`--max-turns` is print-mode only** — ignored in interactive sessions.
7. **Claude may call `python` instead of `python3`** — fails on first try without the symlink, then self-corrects.
8. **Session resumption is directory-scoped** — `--continue` finds the most recent session for the current cwd.
9. **`--json-schema` needs enough `--max-turns`** — Claude must read files before producing structured output.
10. **Trust dialog appears once per directory** — first time only, then cached.
11. **Background tmux sessions persist** — always `tmux kill-session -t <name>` when done.
12. **CJK `send-keys` + Enter in one call drops the Enter** — with a Chinese/Japanese/Korean input method active on macOS, `tmux send-keys -t s "中文…" Enter` sends text but not Enter. Split into two calls: `send-keys "text"` then `send-keys "" Enter`. English-only prompts are safe in one call.
13. **Slash commands only work in interactive mode** — in `-p`, describe the task in natural language.
14. **`--bare` skips OAuth** — needs `ANTHROPIC_API_KEY` or an `apiKeyHelper` in settings.
15. **Context degrades above ~70% window** — monitor with `/context`, proactively `/compact`.
