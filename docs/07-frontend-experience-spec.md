---
title: Gmail Unsubscribe Agent — V1 Frontend Experience
status: proposed
last_updated: 2026-09-14
owners: product, design, frontend
---

# V1 frontend experience

## Product design direction

The interface should feel like a calm **mailroom sorting desk**: dense enough to review hundreds of messages, but explicit about what is evidence, what is a recommendation, and what will cause an external action. It is an operational utility, not an analytics dashboard. The memorable element is the three horizontal sorting trays—Marketing, Unclear, and Non-marketing—with persistent counts and selection summaries. Everything else stays quiet.

### Tokens

| Token | Value | Use |
|---|---|---|
| Paper | `#F6F7F2` | Main background |
| Ink | `#17212B` | Primary text |
| Rule | `#C9CEC7` | Rows and structural dividers |
| Marketing | `#A64B00` | Marketing rail and status icon |
| Unclear | `#7656A7` | Unclear rail and status icon |
| Safe blue | `#246B8E` | Links, focus, non-marketing rail |

Use self-hosted **IBM Plex Sans** for interface copy and tabular figures for counts. Category meaning must always include text/icon, never color alone. Default body size is 16px, evidence 14px, maximum reading line length 76 characters. Visible focus uses a two-pixel Safe blue outline with offset; reduced-motion removes nonessential transitions.

### Layout

Desktop uses a review list plus an evidence drawer, not a grid of interchangeable cards:

```text
┌ Account / scan status ──────────────────────────────────────────────┐
│ Review subscriptions                         7 selected             │
├ Filters ─────────────────────────────────────────────────────────────┤
│ ▾ Marketing                 23 messages · 5 selected                │
│   □ Sender/list      reason + frequency             method          │
│   □ Sender/list      reason + frequency             method          │
│ ▸ Unclear                    8 messages · 2 selected                 │
│ ▸ Non-marketing             31 messages · 0 selected                │
├───────────────────────────────────────────────────────┬──────────────┤
│ Selection remains in context                          │ Evidence     │
│                                      Review 7 actions │ drawer       │
└───────────────────────────────────────────────────────┴──────────────┘
```

Below 800px, the evidence drawer becomes a full-width dialog and the selection summary becomes a sticky bottom bar. Alignment is left throughout; numeric counts align by tabular figures.

## Information architecture and routes

| Route | Primary job | Primary action |
|---|---|---|
| `/setup` | Check backend/OpenAI configuration and connect Gmail | **Connect Gmail** |
| `/scan` | Choose bounds and observe ingestion/classification progress | **Scan email** |
| `/review` | Understand, correct, and select candidates | **Review N actions** |
| `/confirm/:planId` | Verify immutable targets, methods, scopes, and warnings | **Unsubscribe from N lists** |
| `/activity` | Review durable history across all runs and resolve safe repairs | State-specific action only |
| `/activity/:planId` | Follow results and resolve intervention | Context-specific action only |
| `/settings` | Disconnect, revoke, set retention, delete local data | Explicit destructive labels |

The action name stays stable: “Unsubscribe from N lists” on confirmation leads to “Unsubscribe activity,” not generic “Submit” or “Process.”

## Required interaction states

### Setup

- Show separate readiness rows for the Python backend, OpenAI key, Google OAuth client, Gmail read permission, and optional Gmail send permission.
- Explain before OAuth: “The app reads email content to classify it. Sanitized text is sent to OpenAI. Full email bodies are not stored by default.”
- Do not present test fixtures as a usable product mode.

### Scan

- Defaults are visible: **Last 30 days** and **Up to 500 messages**.
- Progress names the current stage: “Finding messages,” “Reading message 84 of 312,” “Classifying,” and “Grouping subscriptions.”
- A reconnecting SSE client shows “Reconnecting to progress…” without implying the backend job stopped.
- Cancellation says what is cancellable: queued reads stop; an in-flight external request may finish.

### Review

- Each category header is a real button with `aria-expanded`, a named region, candidate count, and selected count even when collapsed.
- Nothing is selected on first load. “Select visible” applies only to the current filtered, expanded category and states the number it will select.
- A row shows sender/list, representative subject, frequency/date range, category, concise reason, confidence, and method. **View evidence** opens a sanitized evidence drawer and returns focus to its trigger on close.
- User correction choices are Marketing, Non-marketing, Unclear, and Not a subscription. A correction increments the candidate revision and clears any stale selection.
- Low confidence is expressed as “Needs review,” not a numeric score alone.

### Confirmation

- Group by method: one-click web request, unsubscribe email, and website.
- Show exact list/sender and destination origin. For `mailto:`, show recipient, subject, and body verbatim.
- For website actions, say: “A separate browser window will open. Automation stops for sign-in, CAPTCHA, a different website, or an unclear choice.”
- If `gmail.send` is absent, the primary action becomes **Allow sending unsubscribe email** before final confirmation.
- Any candidate revision or plan-digest mismatch returns to review with: “The selection changed. Review the updated actions before unsubscribing.”

### Activity and intervention

Activity is a chronological dispatch ledger, not a summary-card dashboard. A compact filter strip
offers All actions, Needs attention, Working, Request sent, and Confirmed with visible counts. Every
row contains sender/list name, representative subject, method, redacted destination, localized
timestamp, user-facing status, and the latest safe evidence. `/activity/:planId` shows the same
ledger filtered to one run; `/activity` is available in primary navigation and spans all runs.

| State | User-facing label | Explanation/action |
|---|---|---|
| `executing` | Working | “Opening the unsubscribe page” or method-specific progress. |
| `confirmed` | Unsubscribe confirmed | Sender explicitly acknowledged the request. |
| `submitted` | Request sent | Request left the app, but the sender did not explicitly confirm completion. |
| `needs_user` | Your help is needed | Explain the exact blocker; offer **Take over in browser**, **Resume automation**, or **Stop this action** when applicable. |
| `failed` | Not submitted | Give a concrete reason and show **Review retry** only if policy permits. |

Never use a green success treatment for `submitted`. Status announcements use a polite live region; a batch summary does not steal focus repeatedly. When an intervention dialog opens, focus moves to its heading; closing returns focus to the originating activity row.

Repair controls are evidence-specific. An RFC row exposes **Review one-click retry** only after an
explicit 429/503 and allows one renewed confirmation. A `mailto:` row exposes **Reconnect Gmail**
only when missing authorization proves no send started; after authorization, **Review email send**
requires another explicit click. A browser row resumes or stops the same guarded session. No retry
is offered for submitted, confirmed, mail-send-uncertain, or final-click-uncertain outcomes.

## Empty and failure copy

- Empty marketing category: “No marketing subscriptions found in this scan.”
- All unclear: “These messages need your judgment. Nothing has been selected.”
- OpenAI unavailable: “Classification could not finish. Unresolved messages were placed in Unclear.”
- Gmail permission revoked: “Gmail access ended. Reconnect to continue this scan.”
- Browser blocked or closed: “The separate browser window closed before the outcome was known. Review this action before retrying.”

Errors state what happened and the next safe action. They do not apologize, celebrate, or imply success from transport-only evidence.

## Frontend acceptance checks

- Component tests cover every category accordion, selected-count state, evidence drawer, confirmation method, global activity filter, eligible repair control, result status, empty/error state, and narrow layout.
- Keyboard-only flow covers scan → review → selection → confirmation → results; Escape and focus restoration are deterministic.
- Axe checks cover setup, review with each category state, confirmation, and intervention; manual VoiceOver/NVDA checks are required before V1.
- Forced-colors and reduced-motion modes retain category/status meaning.
- Hostile email strings render only as text; no active HTML, `javascript:` URL, remote image, or inline event executes.
- A controlled browser journey selects synthetic RFC, `mailto:`, and browser candidates together,
  checks submitted/submitted/needs-user evidence, completes the browser intervention, and confirms
  global history without contacting Google or a sender website.
