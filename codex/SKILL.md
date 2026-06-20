---
name: codex
description: "Orchestrate Codex CLI through Hermes using tmux: auth, launch, monitoring, models, commands, and pitfalls."
version: 1.1.0
author: Hermes Agent + OpenAI
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Codex, OpenAI, tmux, PTY, Automation]
    related_skills: [claude-code, hermes-agent]
---

# Codex CLI Hermes Orchestration

Procedural memory for delegating coding work to Codex CLI from a Hermes agent. Keep this operational: use tmux for interactive sessions, capture the pane to monitor, and report results after Codex finishes.

## General Backbone

### 1. Preconditions and Auth

Verify Codex is installed and authenticated before delegation:

```bash
codex --version
codex doctor
codex login
```

Codex supports two OpenAI auth paths:

- **ChatGPT login:** `codex login` opens browser/device auth and caches credentials under `CODEX_HOME` (`~/.codex` by default). This is the default local interactive path.
- **API-key login:** use `codex login` and choose API key auth, or use API-key-specific automation below.

Environment variables:

- `OPENAI_API_KEY`: standard OpenAI API key variable for project code or commands that call OpenAI APIs. Do not assume it authenticates every Codex CLI mode.
- `CODEX_API_KEY`: Codex-supported API key for a single `codex exec` invocation. Prefer inline scope: `CODEX_API_KEY=... codex exec "task"`.
- `CODEX_ACCESS_TOKEN`: ChatGPT/Codex access token for trusted automation; pipe to `codex login --with-access-token`.
- `CODEX_HOME`: relocates Codex state, config, auth, logs, sessions, and skills.

Headless auth:

```bash
codex login --device-auth
printenv CODEX_ACCESS_TOKEN | codex login --with-access-token
```

Treat `~/.codex/auth.json` as a secret. Never paste it into chat, logs, tickets, or commits.

### 2. Launch Pattern: Interactive Codex Under tmux

Use interactive Codex for multi-turn coding work. tmux is the control plane: it gives Hermes a persistent PTY, `send-keys`, and `capture-pane`.

```bash
# Create a named session.
tmux new-session -d -s codex-work -x 140 -y 40

# Start Codex in the target repo. --no-alt-screen makes capture-pane easier to read.
tmux send-keys -t codex-work 'cd /path/to/repo && codex --no-alt-screen --sandbox workspace-write --ask-for-approval on-request' Enter

# Let the TUI initialize, then send the task.
sleep 3
tmux send-keys -t codex-work 'Fix the failing auth tests. Keep the change minimal, run the relevant tests, and report files changed.' Enter

# Monitor progress.
sleep 20
tmux capture-pane -t codex-work -p -S -80

# Send follow-up if needed.
tmux send-keys -t codex-work 'Run the narrowest test command again and summarize remaining failures.' Enter

# Exit when complete.
tmux send-keys -t codex-work '/exit' Enter
tmux kill-session -t codex-work
```

Monitoring cues:

- `Codex is thinking`, command output, diffs, or plan updates means work is still active.
- A visible composer prompt means Codex is waiting for input or finished.
- Permission prompts require input; use `/permissions` if the session is blocked by overly strict policy.
- Use `/status` to confirm model, sandbox, approvals, token usage, and writable roots.
- Use `/diff` or `git diff` after completion before reporting success.

Use `codex exec` only for one-shot automation:

```bash
codex exec "Review the current diff for regressions and return prioritized findings"
codex exec --json "Summarize the repository structure"
codex exec --sandbox workspace-write "Apply the smallest safe fix for the failing unit test"
```

### 3. Model Selection

Default recommendation:

- `gpt-5.5`: start here for most coding, refactoring, review, debugging, planning, and research tasks.
- `gpt-5.4-mini`: use for faster or lower-cost lightweight tasks and subagents.
- `gpt-5.3-codex-spark`: research-preview, near-instant coding iteration model for eligible ChatGPT Pro users.

Set a model when launching:

```bash
codex --model gpt-5.5
codex -m gpt-5.4-mini "Review this diff for obvious bugs"
codex exec --model gpt-5.5 "Fix the flaky test"
```

Set a default model in `~/.codex/config.toml` or project `.codex/config.toml`:

```toml
model = "gpt-5.5"
model_reasoning_effort = "high"
```

Switch inside an active TUI:

```text
/model
/status
```

Do not use deprecated Codex model names in new scripts. If a model is rejected, run `codex debug models` to inspect the current catalog available to that install/auth context.

### 4. Key Flags

Use these frequently:

```bash
codex --cd /path/to/repo "task"
codex --model gpt-5.5 "task"
codex --sandbox workspace-write --ask-for-approval on-request "task"
codex --add-dir ../shared "task"
codex --search "task needing current web data"
codex --image screenshot.png "Explain this error"
codex --profile work "task"
codex -c model_reasoning_effort=high "task"
codex --no-alt-screen "task"
```

Safety flags:

- `--sandbox read-only`: review/planning only.
- `--sandbox workspace-write`: normal coding in the repo.
- `--sandbox danger-full-access`: only inside an externally hardened environment.
- `--ask-for-approval on-request`: good interactive default.
- `--ask-for-approval never`: use only when external controls make approval prompts impossible.
- `--dangerously-bypass-approvals-and-sandbox` / `--yolo`: avoid unless the user explicitly wants full access and the environment is disposable or hardened.

Useful subcommands:

```bash
codex login
codex logout
codex doctor
codex resume --last
codex exec "task"
codex exec resume --last "continue"
codex apply <TASK_ID>
codex cloud
codex mcp list
codex features list
codex debug models
codex update
```

### 5. Key Slash Commands

Use slash commands through `tmux send-keys` when the TUI is active:

```text
/model          choose active model and effort
/permissions    adjust sandbox/approval behavior
/status         inspect model, approvals, roots, context, usage
/diff           inspect current working-tree changes
/review         run Codex review on local changes
/plan           switch to planning mode
/compact        summarize long context
/clear          start a fresh chat in the same TUI
/new            start a new conversation
/resume         resume a saved conversation
/fork           branch the current conversation
/side or /btw   side question without derailing the main thread
/mcp            inspect MCP tools
/skills         browse/use installed skills
/init           create AGENTS.md
/logout         clear credentials
/exit or /quit  leave the session
```

Queued input: while Codex is running, press `Tab` after typing a follow-up or slash command to queue it for the next turn.

## Machine Appendix: Hermes + tmux

### ⚠️ Never go silent — poll after every interaction
After **every** `send-keys` (task, slash command, or approval choice), `capture-pane` again in **3–5 s** to confirm the input landed and Codex advanced — a dropped Enter or a fresh approval prompt is invisible otherwise. Keep polling until Codex is **idle/done, errored, or waiting**, and surface any approval prompt / plan / numbered selection to the user **the instant it appears, unprompted**. "Sent" is not "done." Full pattern: the [`agent-manager` Prime directive](../agent-manager/SKILL.md#️-prime-directive--never-go-silent).

### Standard Hermes Recipe

Use separate terminal calls rather than one giant shell line when possible; each step is easier to inspect and retry.

```python
terminal(command="tmux new-session -d -s codex-work -x 140 -y 40")
terminal(command="tmux send-keys -t codex-work 'cd /path/to/repo && codex --no-alt-screen --model gpt-5.5 --sandbox workspace-write --ask-for-approval on-request' Enter")
terminal(command="sleep 3 && tmux send-keys -t codex-work 'Implement the requested change. Run focused tests. Stop and report blockers.' Enter")
terminal(command="sleep 20 && tmux capture-pane -t codex-work -p -S -100")
```

Recommended session naming:

- `codex-<short-task>` for one active task.
- `codex-review` for review-only runs.
- `codex-fix-<area>` for implementation runs.

Capture strategy:

```bash
tmux capture-pane -t codex-work -p -S -60
tmux capture-pane -t codex-work -p -S -200
tmux list-sessions
tmux kill-session -t codex-work
```

If output is hard to read, restart with `--no-alt-screen` and a wide pane (`-x 140 -y 40` or larger).

### Permission Handling

For most repo work:

```bash
codex --sandbox workspace-write --ask-for-approval on-request
```

For review-only:

```bash
codex --sandbox read-only
```

For automation:

```bash
codex exec --sandbox read-only "review the current diff"
codex exec --sandbox workspace-write "make the smallest safe fix"
```

Do not jump to `--yolo` to avoid prompts. First try `/permissions`, `--add-dir`, project config, or a narrower task.

### Completion Checklist Before Reporting

Before telling the user Codex finished:

1. Capture the pane and confirm Codex is idle or explicitly done.
2. Check `git status --short`.
3. Inspect `git diff` or ask Codex `/diff`.
4. Run or confirm the relevant tests.
5. Summarize files changed, tests run, and unresolved risks.
6. Kill tmux sessions you started unless the user wants them left running.

### Codex-Specific Pitfalls

- Interactive Codex is a TUI. Use tmux; plain background execution loses the ability to monitor and respond.
- `OPENAI_API_KEY` is not the documented universal Codex CLI login switch. Use `codex login` for persistent auth and `CODEX_API_KEY` inline for `codex exec` API-key automation.
- `codex exec` starts read-only by default. Add `--sandbox workspace-write` if edits are expected.
- Project `.codex/config.toml`, hooks, and rules only load when the project is trusted.
- Linux/WSL sandboxing depends on `bubblewrap`/user namespaces; run `codex doctor` if commands fail unexpectedly.
- Network access is sandbox/approval dependent. Use `--search` for live web search; otherwise local tasks normally use cached web search.
- `danger-full-access`, `--yolo`, and `approval_policy = "never"` remove important guardrails. Use only with explicit user intent or isolated runners.
- Saved sessions are scoped by working directory unless using broader resume options. Start Codex in the target repo and use `--cd` for clarity.
- `codex cloud` and local CLI runs are different surfaces. Local `/model` and `--model` do not control cloud task model selection.
- Always inspect the working tree yourself after Codex edits; do not rely only on the TUI summary.
- **CJK `send-keys` + Enter in one call drops the Enter** — with a Chinese/Japanese/Korean input method active on macOS, `tmux send-keys -t s "中文…" Enter` sends text but not Enter. Split into two calls (`send-keys "text"` then `send-keys "" Enter`), or inject via paste buffer: `printf '%s' "中文…" | tmux load-buffer -b k -; tmux paste-buffer -t s -b k -d; tmux send-keys -t s C-m`. English-only prompts are safe in one call.
- **Don't report "sent" as "done"** — after every `send-keys`, `capture-pane` in 3–5 s to confirm Codex actually advanced and surface any approval prompt immediately (see "Never go silent" above).
