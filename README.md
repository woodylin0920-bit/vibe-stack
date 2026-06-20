# vibe-stack

A Hermes skill playbook for **controlling coding agents from your phone** — spawn agents, assign tasks, review output, and merge work, all via chat. Watch a session in a mobile/web app; steer it from a chat message.

**New here?** Start with **[GETTING-STARTED.md](GETTING-STARTED.md)** — a cloud-first quickstart.

## Skills

| Skill | What it does |
|-------|--------------|
| [`agent-manager`](agent-manager/SKILL.md) | The **control plane** — open an agent (Claude Code / Codex / OpenCode) in a project, send tasks, drive slash commands and control keys remotely, detect interactive prompts, check status, and handle auth. Scales to **multi-agent fleets**: lanes (worktree + branch + session + log), race mode, a review gate, and a merge captain — spawn agents, assign tasks, review, and merge work, all from chat. |
| [`claude-code`](claude-code/SKILL.md) | Deep orchestration guide for the **Claude Code CLI** — print vs interactive PTY modes, the essential flag reference, settings & `CLAUDE.md` hierarchy, slash commands, hooks, subagents, MCP, PR-review patterns, and `--remote-control`. |
| [`codex`](codex/SKILL.md) | Orchestration guide for the **OpenAI Codex CLI** — one-shot `codex exec`, `--full-auto` / `--yolo` modes, PTY + git-repo requirements, background/tmux driving, and PR review. |
| [`coffee-time`](coffee-time/SKILL.md) | Multi-agent **brainstorm** — fan one question to N agents on intentionally different models, run them independently, synthesize with Opus, and present options to the user. |

## Contents

```
agent-manager/
  SKILL.md    # remote control plane for coding agents
claude-code/
  SKILL.md    # Claude Code CLI orchestration guide
codex/
  SKILL.md    # OpenAI Codex CLI orchestration guide
coffee-time/
  SKILL.md    # multi-agent brainstorm mode
dashboard/
  server.py   # real-time agent dashboard (phone-friendly)
docs/
  deployment.md  # run the orchestrator on a VPS (recommended) or macOS
GETTING-STARTED.md  # cloud-first quickstart
```

## Install as a Hermes skill

One-liner per skill:

```bash
hermes skills install https://raw.githubusercontent.com/woodylin0920-bit/vibe-stack/main/agent-manager/SKILL.md
hermes skills install https://raw.githubusercontent.com/woodylin0920-bit/vibe-stack/main/claude-code/SKILL.md
hermes skills install https://raw.githubusercontent.com/woodylin0920-bit/vibe-stack/main/codex/SKILL.md
```

## Install as a Claude Code skill

Drop a skill folder into your skills directory:

```bash
# Personal (all projects)
mkdir -p ~/.claude/skills
cp -r agent-manager claude-code codex ~/.claude/skills/

# or Project-scoped (team-shared, git-tracked)
mkdir -p .claude/skills
cp -r agent-manager claude-code codex .claude/skills/
```

Claude Code auto-discovers skills in `.claude/skills/` and invokes them by natural language when a task matches the skill's `description`.

## Deployment

The orchestrator runs the same on a Mac or a Linux VPS — see **[docs/deployment.md](docs/deployment.md)** for always-on setup (launchd vs systemd), the macOS keep-awake note, Telegram wiring, and a Mac-vs-cloud trade-off table. Platform-agnostic; pick what fits.

## Use as a reference

Each `SKILL.md` also works standalone — read it as a cheat sheet for driving coding-agent CLIs.

## License

MIT
