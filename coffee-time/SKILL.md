---
name: coffee-time
description: "Multi-agent brainstorm mode — fan one question out to N agents on intentionally different models, run them independently, then synthesize the perspectives with Opus and present options to the user."
version: 1.0.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Brainstorm, Multi-Agent, Synthesis, Diversity, Orchestration]
    related_skills: [agent-manager, claude-code, codex]
---

# Coffee-time — multi-agent brainstorm mode

Pour a coffee, ask a hard question, get a synthesized answer. Coffee-time fans **one question** out to **N agents on intentionally different models**, runs them independently for genuine diversity of perspective, then has **Opus synthesize** the results and present **options to the user**.

It's the divergent cousin of [`agent-manager`](../agent-manager/SKILL.md)'s race mode:

| | **race mode** (agent-manager) | **coffee-time** (this skill) |
|---|---|---|
| Input | a coding **task spec** | an open **question / problem** |
| Output | one winning **diff**, merged | a **synthesis** of perspectives + options |
| Goal | convergent — best implementation | divergent — best thinking |
| Changes code? | yes (worktrees/branches) | no (read-only; just ideas) |

**Who decides:** coffee-time follows the vibe-stack rule — the **user is the brain.** Hermes aggregates the panel and synthesizes, then **presents options; it does not pick the answer.**

## When to use
- Open-ended design / strategy / product questions ("what should we build next?", "how should we price this?").
- Framing a fuzzy problem, generating approaches, stress-testing an idea from multiple angles.
- **Not** for well-scoped implementation — use race mode for that.

## Why different models (diversity is the point)
Running the same question on five copies of one model gives you one perspective five times. Different model families reason differently — **diversity of model = diversity of perspective.** Pick a panel that disagrees:

| Panel seat | Model | Brings |
|------------|-------|--------|
| Depth | **Opus 4.8** (`--model opus --effort high`) | deepest reasoning, long-horizon tradeoffs |
| Pragmatism | **Sonnet** (`--model sonnet`) | fast, grounded, practical takes |
| Different lineage | **GPT-5.5** via Codex (`codex exec`) | a genuinely different training/lineage view |
| Wildcard (optional) | **OpenCode** w/ another provider (`opencode run --model …`) | a 4th independent angle |

3–4 seats is plenty. (See [`agent-manager` → Model routing](../agent-manager/SKILL.md#model-routing--match-the-model-to-the-job).)

## The recipe

### 1. Frame the question
One clear prompt + any needed context. Save it so every agent gets the identical input:
```bash
mkdir -p /tmp/coffee && Q="How should we price vibe-stack for individual developers vs teams? Give concrete options with tradeoffs."
```

### 2. Fan out — independently, in parallel
Brainstorm is read-only, so bounded one-shots are ideal (no tmux/worktrees needed). Run them concurrently, each capturing to its own file:
```bash
claude -p "$Q" --model opus   --effort high --max-turns 6 > /tmp/coffee/opus.md   2>&1 &
claude -p "$Q" --model sonnet               --max-turns 6 > /tmp/coffee/sonnet.md 2>&1 &
(cd /path/to/a/git/repo && codex exec "$Q")                > /tmp/coffee/gpt55.md  2>&1 &   # Codex needs a git repo + PTY
opencode run "$Q" --model openrouter/google/gemini-2.5-pro > /tmp/coffee/oc.md     2>&1 &   # optional wildcard
wait
```
Keep every raw answer — the user may want to read the originals, not just the synthesis. **Never go silent:** tell the user the panel is running and report when it's collected (see [agent-manager Prime directive](../agent-manager/SKILL.md#️-prime-directive--never-go-silent)).

### 3. Synthesize with Opus
A dedicated synthesis pass — cluster, compare, and surface options **without choosing**:
```bash
cat /tmp/coffee/*.md | claude -p "You are synthesizing a brainstorm from several independent agents on different models. \
Cluster the ideas into themes. Note where they AGREE and where they DISAGREE (and why). \
Surface the strongest *distinct* ideas with their tradeoffs. End with 2–4 clear OPTIONS for the user to choose between. \
Do NOT pick one yourself — the user decides." --model opus --effort high > /tmp/coffee/SYNTHESIS.md
```

### 4. Present to the user
Send the synthesis: **themes → consensus → disagreements → 2–4 options (with tradeoffs)**, and offer the raw per-agent answers on request. Then stop — the user picks the direction.

## Worked example
Question: *"What's the wedge feature for vibe-stack's first release?"*
1. Fan out to Opus / Sonnet / GPT-5.5 (+ optional 4th).
2. Synthesis (Opus) finds: **consensus** on "remote agent control from phone"; **disagreement** on whether to lead with single-agent control vs fleets; two surfaced options — (A) ship single-agent remote control polished, (B) ship the fleet/kanban story.
3. Hermes presents A vs B with tradeoffs → **user chooses**.

## Pitfalls
- **Same model on every seat** — defeats the purpose; vary models deliberately.
- **Hermes picking the winner** — it synthesizes and presents options; the *user* decides.
- **Too many seats** — 3–4 distinct perspectives beat 10 near-duplicates; cap it.
- **Throwing away raw outputs** — keep each agent's answer; the synthesis is lossy.
- **Using coffee-time for code** — implementation belongs in race mode (real diffs, gated merges), not here.
- **Codex seat fails outside a git repo** — `codex exec` needs one; run it from a repo or drop that seat.
