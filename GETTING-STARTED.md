# Getting started with vibe-stack

vibe-stack lets you **control coding agents from your phone** — spawn agents, assign tasks, review output, merge work — by messaging an orchestrator on any channel.

**The model:** `User → [any channel: Telegram / LINE / Slack / web / CLI] → Hermes (orchestrator) → agents.` The **user is the brain and decision-maker**; the orchestrator is the right hand — it aggregates, coordinates, executes, and reports, and surfaces real decisions rather than making them. vibe-stack is **channel-agnostic** by design.

## The fastest path: a cloud VPS (recommended)

A small Linux VPS is the simplest way to run this — always-on, no sleep issues, fixed IP, SSH built in. Prefer your Mac instead only if you need local files, GUI agents, or desktop automation (see the [Mac section](docs/deployment.md#alternative-run-it-on-your-mac-local)).

1. **Spin up a VPS** — Hetzner / DigitalOcean / Vultr, Ubuntu LTS, 2 vCPU / 4 GB.
2. **Install** the orchestrator + the agent CLIs you'll drive (Claude Code, Codex, OpenCode).
3. **Connect a channel** — e.g. a Telegram bot token in the orchestrator config (any supported channel works).
4. **Make it always-on** — a `systemd` service (auto-start + auto-restart).
5. **Message it from your phone** — it answers whether or not any laptop is open.

Full step-by-step (commands, systemd unit, auth): **[docs/deployment.md](docs/deployment.md)**.

## Then learn the skills

| Skill | Use it to |
|-------|-----------|
| [`agent-manager`](agent-manager/SKILL.md) | The control plane — open agents, send tasks, drive slash commands/keys remotely, run multi-agent **fleets** (lanes, race mode, review gate, merge captain), with model routing and the goal-driven `/loop`. **Start here.** |
| [`claude-code`](claude-code/SKILL.md) | Drive the Claude Code CLI (print vs interactive, flags, `--remote-control`). |
| [`codex`](codex/SKILL.md) | Drive the OpenAI Codex CLI. |
| [`coffee-time`](coffee-time/SKILL.md) | Multi-agent **brainstorm** — fan a question to N models, synthesize with Opus, present options. |

Install a skill:
```bash
hermes skills install https://raw.githubusercontent.com/woodylin0920-bit/vibe-stack/main/agent-manager/SKILL.md
```

## Two principles that run through everything
- **Never go silent** — after dispatching work, the orchestrator keeps watching (poll after every interaction) and surfaces prompts/blockers the instant they appear.
- **Drive to the goal, escalate every real decision** — it self-heals the mechanical path toward your goal, but every irreversible/ambiguous/taste call comes back to you. The user decides.

## Optional: the dashboard
A single-file web dashboard shows live agent sessions (working/idle/blocked), output, and a git-derived kanban, with per-agent controls — open it from your phone. See [`dashboard/`](dashboard/) — run `python3 dashboard/server.py`.
