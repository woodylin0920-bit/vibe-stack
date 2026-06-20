# Telegram-native UX for vibe-stack

How vibe-stack should *feel* on Telegram: a calm, glanceable control surface — one
live status you can read at a glance, and a button for every decision. Never a wall
of notifications.

This doc is the design source of truth. It states the **ideal**, then maps it onto
**what the Hermes gateway actually exposes to a skill today** (verified against
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent) source),
implements the supported parts, and files the gaps as GitHub issues.

> **Channel-agnostic, but Telegram-first.** Everything here is expressed in Telegram
> terms because Telegram is the reference channel, but the *principles* (one live
> status, button-per-decision, never spam) are channel-agnostic — see
> [`agent-manager`](../agent-manager/SKILL.md#channel-agnostic-by-design).

---

## Design principles

1. **Never spam.** The orchestrator emits a message only when something *meaningful
   changed*. No heartbeats, no per-line narration, no "still working…" pings. Silence
   is the default; a message is an event.
2. **Edit in place.** Status is *updated*, not *re-sent*. One message mutates over
   time instead of a growing column of stale snapshots.
3. **Every action is a button.** A decision the user must make is a tap, never a typed
   command. The user should be able to run an overnight session with their thumb.
4. **Status = one pinned message; events = ephemeral.** A single pinned dashboard
   shows "what is true right now." Discrete events (a decision needed, a task done)
   are separate, short, and disposable.

---

## The ideal (target design)

### A. Edit-in-place live dashboard — one pinned message

A single message, pinned silently to the top of the chat, updated in place as the
fleet changes:

```
🤖 vibe-stack · 3 agents · 02:14
─────────────────────────────
🔵 claude-feat-x   working   · auth refactor (4/12 tests)
🟡 codex-api       waiting   · permission: write outside repo
🟢 claude-docs     idle      · finished · ready to merge
─────────────────────────────
main: 2 lanes ahead · last merge 23m ago
```

- Sent **once**, `message_id` retained, **edited** on every meaningful change
  (`editMessageText`).
- **Pinned silently** (`pinChatMessage` with `disable_notification=true`) so it sits at
  the top without buzzing.
- **Diffed before every edit** — only call the API when the rendered text actually
  changed, to dodge `Bad Request: message is not modified` *and* conserve the
  ~1-edit/sec-per-chat rate budget. Comfortable cadence: **3–5 s**.

### B. Inline buttons on agent-complete

When a lane finishes, the user gets one actionable message:

```
✅ claude-feat-x finished — auth refactor
   12/12 tests green · 3 files · +148 −22

   [ ✅ Merge ]  [ 👀 Diff ]  [ 🔄 Keep working ]
```

- Buttons via `InlineKeyboardMarkup`; taps arrive as a `callback_query`.
- On tap: **answer immediately** (`answerCallbackQuery`, clears the phone spinner),
  **authorize** on `from.id`, act, then **edit the message** to the outcome
  (`✅ Merged claude-feat-x`) with the keyboard removed — so a decision can't be
  double-tapped.
- `callback_data` stays ASCII and ≤64 bytes, encoded `action:lane` (e.g.
  `merge:feat-x`); emoji live in the button `text` only.

### C. Ephemeral events

Low-priority notices (an agent woke, a nudge landed) are sent silently
(`disable_notification=true`) and `deleteMessage`d once superseded (within Telegram's
48 h delete window). The pinned dashboard is the durable record; events are noise that
cleans itself up.

---

## Reality: what Hermes exposes to a skill **today**

A skill never calls the Telegram Bot API directly — it goes through the Hermes
gateway's **tool layer**. That layer is deliberately platform-agnostic and **minimal**.
The rich Telegram machinery (edit-in-place, inline keyboards, callback routing) lives
in the gateway's *internal* Telegram adapter and drives only built-in flows — it is
**not reachable from a skill**. (Verified by reading `tools/send_message_tool.py`,
`tools/clarify_tool.py`, and `plugins/platforms/telegram/adapter.py` on `main`.)

| Capability | Skill-facing? | Today | Exact mechanism |
|---|---|---|---|
| Send a message | ✅ yes | **SUPPORTED** | `send_message(action="send", target="telegram[:chat[:thread]]", message="…")`; attach files via a `MEDIA:/path` marker |
| List targets | ✅ yes | **SUPPORTED** | `send_message(action="list")` |
| Buttons + receive the tap | ⚠️ partial | **SUPPORTED via `clarify` only** | `clarify(question, choices=[…≤4])` → renders **one inline button per choice** on Telegram, returns the tapped value to the agent synchronously |
| Reactions | ✅ yes | **SUPPORTED** | `send_message(action="react"/"unreact", emoji=…, message_id=…)` |
| Edit a prior message (edit-in-place) | ❌ no | **NOT exposed** | adapter has `edit_message`/`editMessageText` internally; no `edit` action and no message-id handle on `send_message` |
| Arbitrary inline keyboard + custom `callback_data` | ❌ no | **NOT exposed** | adapter's inline keyboards are hard-wired to built-in prefixes (`ea:`, `sc:`, `mp:`, clarify); a skill can't register a new callback |
| Silent / no-notification per message | ❌ no | **CONFIG ONLY** | global mode `important` (default) vs `all` via `HERMES_TELEGRAM_NOTIFICATIONS` — not a per-call flag |
| Pin / unpin | ❌ no | **NOT in codebase** | no `pinChatMessage` anywhere in the adapter |
| Delete a message | ❌ no | **NOT exposed** | adapter `delete_message` is internal-only |

> **The one big lever we *do* have:** `clarify` renders real inline buttons and feeds
> the tap back into the agent. Our **entire button-per-decision principle is buildable
> today** on `clarify`. The dashboard's *edit-in-place + pin* half is not — so we
> degrade it gracefully (below) and file the gaps upstream + locally.

### `clarify` — the headline primitive

```
clarify(
  question = "✅ claude-feat-x finished — auth refactor (12/12 green, +148 −22). What now?",
  choices  = ["✅ Merge", "👀 Show diff", "🔄 Keep working"]   # ≤ 4; renders as inline buttons
)
# → returns the tapped label, e.g. "✅ Merge", straight back to the orchestrator.
```

- **Max 4 choices** (`MAX_CHOICES = 4`) — our three-button complete-prompt fits with
  room to spare (a 4th, e.g. `🗑 Discard`, is free).
- Open-ended `clarify` (no `choices`) renders no buttons and captures the user's next
  message instead — use it when the answer is free-form.
- It **blocks** until the user answers (timeout `agent.clarify_timeout`, default 600 s).
  That's exactly the Decision-Gate semantics: stop, ask with buttons, act on the tap.

---

## What we build today (mapping ideal → supported)

| Ideal | Today's implementation | Degraded vs ideal? |
|---|---|---|
| **Button per decision** (Merge/Diff/Keep working) | `clarify(question, ["✅ Merge","👀 Show diff","🔄 Keep working"])` | **No** — full fidelity. |
| **Never spam** | `vibe-poll` keeps a per-session state fingerprint and emits **only on state transition**; silent otherwise. The orchestrator relays poll output via `send_message` *only when there is output*. | **No** — the spirit ("a message is an event") is fully met. |
| **One live dashboard, edited in place** | Can't edit/pin from a skill. Degrade to **send-the-dashboard-only-when-it-changed** (`vibe-poll --digest`): one consolidated message per meaningful change, not a stream. | **Partial** — it's a fresh message, not an in-place edit. Tracked as issue ① + ③. |
| **Pinned status** | Not possible from a skill. The most-recent digest is the de-facto status. | **Yes** — tracked as issue ②. |
| **Ephemeral / auto-delete events** | Not possible from a skill. Mitigated by emitting rarely (dedup) so there's little to clean up. | **Partial** — tracked as issue ④. |

The **poller** (`bin/vibe-poll`) is the engine for "never spam": it diffs the current
fleet state against the last poll and prints a digest **only when a session changed
state** (e.g. `working → waiting-input`, `working → idle`). It flags decision-points
with a `[DECISION …]` marker so the orchestrator knows to raise a `clarify` button
prompt. See [`bin/vibe-poll`](../bin/vibe-poll) and the
[`overnight`](../overnight/SKILL.md) skill for the loop that consumes it.

### The overnight loop, in Telegram terms

```
backlog → dispatch lanes (agent-manager)
loop every 30–60s:
    vibe-poll                              # silent unless a session changed state
    └─ output? → send_message(telegram)    # relay the digest (never spam: only on change)
    └─ [DECISION] line?
         ├─ done  → clarify("<lane> finished…", ["✅ Merge","👀 Show diff","🔄 Keep working"])
         └─ wait  → clarify("<lane> needs input: <prompt>", [the agent's options])
    act on the tapped choice (merge / show diff / nudge / keep working)
morning → one send_message summary (what merged, what's blocked)
```

---

## Hermes API calls needed (exact, available today)

```python
# 1. Relay a status digest (only when vibe-poll produced output)
send_message(action="send", target="telegram", message=<digest>)

# 2. Ask a decision with inline buttons, get the tap back
choice = clarify(
    question="✅ claude-feat-x finished — auth refactor (12/12 green). What now?",
    choices=["✅ Merge", "👀 Show diff", "🔄 Keep working"],
)

# 3. Surface a diff inline (Diff button path) — send, then re-ask
send_message(action="send", target="telegram", message="```diff\n"+diff+"\n```")
choice = clarify(question="Merge claude-feat-x?", choices=["✅ Merge", "🔄 Keep working"])

# 4. (optional) acknowledge with a reaction instead of a message
send_message(action="react", target="telegram", emoji="👍", message_id=<id>)
```

Silent delivery is set **once** at deploy time, not per call:
`HERMES_TELEGRAM_NOTIFICATIONS=important` (default) keeps tool-progress quiet and only
rings for answers/approvals — which is exactly what we want for the poll digests.

---

## What is NOT yet supported → GitHub Issues

Filed on [`woodylin0920-bit/vibe-stack`](https://github.com/woodylin0920-bit/vibe-stack/issues).
Each blocks one piece of the ideal; each is unblocked the moment the Hermes gateway
exposes the underlying adapter capability to skills (the adapter already implements
most of these internally).

1. **Edit-in-place for status messages.** Need a `send_message(action="edit",
   message_id=…)` or a returned editable handle, so the live dashboard mutates instead
   of being re-sent. *Upstream:* the adapter already has `edit_message` /
   `editMessageText` — it just isn't on the tool. (Tracks hermes feature-request
   #15311 / #21469.)
2. **Pin / unpin from a skill.** Need `pin`/`unpin` actions so the dashboard can be
   pinned silently. *Upstream:* not present in the adapter at all — a true gap.
3. **Arbitrary inline keyboards with custom `callback_data` (>4, persistent,
   non-blocking).** `clarify` covers blocking ≤4-choice prompts; we still want
   always-visible action buttons on a status message and >4 options. *Upstream:* adapter
   keyboards are hard-wired to built-in prefixes; no skill-registerable callback.
4. **Delete / ephemeral messages from a skill.** Need a `delete` action so event
   notices can clean themselves up. *Upstream:* adapter `delete_message` is
   internal-only.
5. **Per-message silent flag.** Need a `silent=true` param on `send_message` rather than
   the global `important`/`all` mode, so a noisy digest can be silent while a real
   decision rings.

Each issue should link back to this doc and note the verified upstream status so that
when Hermes ships the capability, the corresponding degraded path here is swapped for
the ideal.

---

## Appendix — Telegram Bot API reference (for when Hermes exposes it)

The primitives the ideal design is built on, so the swap is mechanical once available:

| Need | Method | Key params / notes |
|---|---|---|
| Edit text in place | `editMessageText` | `chat_id`+`message_id`, `text` (≤4096); returns the `Message`. **Diff before calling** to avoid `message is not modified`. |
| Edit only buttons | `editMessageReplyMarkup` | cheap; no text reflow. |
| Pin silently | `pinChatMessage` | `disable_notification=true`. |
| Unpin | `unpinChatMessage` | omit `message_id` to unpin the latest. |
| Delete | `deleteMessage` | own/visible messages **< 48 h** old. |
| Silent send | `sendMessage` | `disable_notification=true`. |
| Buttons | `InlineKeyboardMarkup` / `InlineKeyboardButton` | `callback_data` **1–64 bytes**, ASCII; emoji in `text`. |
| Tap arrives | `callback_query` update | `from.id` (authorize!), `data`, `message.message_id`. |
| Ack a tap | `answerCallbackQuery` | call **first** (clears spinner); `text` ≤200, `show_alert`. |

**Rate limits:** ~1 message/edit per second per chat (shared across send/edit/pin);
~30/sec globally; 429 returns `parameters.retry_after` — sleep exactly that long.
Serialize all calls through one queue and diff-before-edit.

### Prior art worth reading
- [`grinev/opencode-telegram-bot`](https://github.com/grinev/opencode-telegram-bot) —
  closest analog: an AI coding agent with a **single pinned live-status message edited
  in place** + ephemeral background notifications. The reference implementation for the
  ideal once Hermes exposes edit/pin.
- [`python-telegram-bot` inline-keyboard examples](https://github.com/python-telegram-bot/python-telegram-bot/blob/master/examples/inlinekeyboard.py) —
  canonical answer-then-edit button flow.

---

*Verified against `NousResearch/hermes-agent` `main` and
[core.telegram.org/bots/api](https://core.telegram.org/bots/api), June 2026.*
