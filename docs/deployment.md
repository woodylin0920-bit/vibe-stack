# Deploying the orchestrator

The orchestrator (e.g. Hermes) is the always-on process that receives your messages — on **any channel** (Telegram, LINE, Slack, web, CLI) — and drives coding agents. It can run on a cloud VPS or on your Mac.

> **Recommended: a Linux VPS (cloud).** It's the simpler path for most people — always-on, no sleep issues, a fixed public IP, and SSH built in. Run it on your **Mac** only if you specifically need local file access, GUI agents, or desktop automation (see [Alternative: run it on your Mac](#alternative-run-it-on-your-mac-local)).

---

## Recommended: Linux VPS (cloud)

### 1. Pick a VPS
Any small Linux VPS works: Hetzner CX22 (2 vCPU / 4 GB, ~€4/mo), DigitalOcean Basic (2 GB, ~$12/mo), Vultr/Linode/Lightsail. 2 vCPU / 4 GB handles the orchestrator plus a few agents. Ubuntu 22.04/24.04 LTS is the easy default; pick a region near you for low latency.

### 2. Provision the base
```bash
ssh root@<vps-ip>
adduser hermes && usermod -aG sudo hermes        # non-root user
apt update && apt install -y git tmux python3 python3-venv curl
# install the agent CLIs you'll drive:
npm i -g @anthropic-ai/claude-code @openai/codex   # + opencode, per each agent's docs
```

### 3. Install the orchestrator
Install your orchestrator (Hermes or equivalent) per its own docs. Broadly:
```bash
su - hermes
git clone <orchestrator-repo> ~/.hermes && cd ~/.hermes
python3 -m venv venv && ./venv/bin/pip install -e .
```

### 4. Connect a channel (Telegram shown; any channel works)
1. Create a bot with [@BotFather](https://t.me/BotFather); copy the token.
2. For group use, turn **off** the bot's privacy mode so it can read group messages.
3. Put the token + allowed chat IDs in the orchestrator config (e.g. `~/.hermes/.env`):
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   ```
4. It long-polls the channel — **no inbound port or public webhook needed** (tiny attack surface, works behind NAT). vibe-stack is channel-agnostic; swap Telegram for any channel the orchestrator supports.

### 5. Always-on via systemd
Auto-start on boot, auto-restart on crash:
```ini
# /etc/systemd/system/hermes.service
[Unit]
Description=Orchestrator gateway
After=network-online.target
Wants=network-online.target

[Service]
User=hermes
WorkingDirectory=/home/hermes/.hermes
ExecStart=/home/hermes/.hermes/venv/bin/python -m hermes_cli.main gateway run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hermes
sudo systemctl status hermes      # verify
journalctl -u hermes -f           # live logs
```
Now message your bot from your phone — it answers whether or not any laptop is open. **No keep-awake, no Tailscale, no GUI** — that's why cloud is the recommended default.

### 6. Auth for the agents
Run each agent's login once over SSH (`claude auth login`, `codex login`, `opencode auth login`). When an OAuth URL appears, open it on your phone and approve. For unattended re-auth later, prefer long-lived credentials so you never need a desktop browser on the VM: `claude setup-token` / `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, provider keys (`OPENROUTER_API_KEY`). Remote re-auth flow (surface the login URL to the user via chat) is in [`agent-manager`](../agent-manager/SKILL.md).

---

## Alternative: run it on your Mac (local)

Choose the Mac when the work genuinely needs it: **local file access**, **GUI agents / desktop automation** (Terminal.app, browser control, AppleScript, screen-watching), or macOS-only tooling. The trade-off is that a laptop isn't built to be an always-on server.

### Always-on via launchd
```xml
<!-- ~/Library/LaunchAgents/ai.hermes.gateway.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>ai.hermes.gateway</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/.hermes/venv/bin/python</string>
    <string>-m</string><string>hermes_cli.main</string>
    <string>gateway</string><string>run</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
```
```bash
launchctl load -w ~/Library/LaunchAgents/ai.hermes.gateway.plist
launchctl list | grep hermes
```

### Keep it awake (macOS only)
launchd keeps the *process* alive, but macOS sleeps the *machine* on lid-close/idle, which suspends the gateway and freezes every tmux agent. Two options:
- **Persistent `caffeinate`** (lid stays open): a LaunchAgent running `/usr/bin/caffeinate -i -m -s`. Simple, reversible, works on battery.
- **`sudo pmset -c disablesleep 1`** (allows lid-closed on AC): no caffeinate, but requires AC and is a system-wide change.

### Reach it from your phone
A Mac has no fixed public IP, so:
- **Same WiFi:** `http://<mac-lan-ip>:<port>`.
- **From anywhere:** install **Tailscale** on the Mac and phone, use the Tailscale IP/name.

None of this is needed on a cloud VPS — which is exactly why cloud is the default recommendation.

---

## Platform differences (reference)

| Concern | Linux VPS (recommended) | macOS (local) |
|---------|-------------------------|---------------|
| Stays on by default? | **Yes** | No — needs keep-awake |
| Service manager | `systemd` | `launchd` |
| Reach from anywhere | Fixed public IP + SSH | Needs Tailscale |
| Survives reboot/power loss | Unattended | After login; keep-awake resets |
| GUI agents / desktop automation | No (headless) | **Yes** |
| Local file access | Files on the VPS | Your Mac's files |
| Cost | ~€4–12/mo | Free HW, battery/heat if kept awake |

You can run both and pick per task; the same skills (`agent-manager`, `claude-code`, `codex`, `coffee-time`) work on either host — only the host differs.
