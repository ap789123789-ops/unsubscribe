---
title: Gmail Unsubscribe Agent — V1 Project Plan
status: implemented-awaiting-credentialed-release
last_updated: 2026-09-14
owners: maintainers
---

# V1 project plan

> Implementation status (2026-09-14): all eight code slices and the non-credentialed automated
> gate are implemented. V1 is not release-certified until `make smoke-real-read` succeeds with a
> dedicated Gmail account/OpenAI key, the controlled destructive executor gate succeeds, and the
> manual accessibility/security checklist is completed.

## Outcome

Build a local-first, open-source web app that connects to one real Gmail account, scans a bounded slice of mail, classifies messages as **marketing**, **non-marketing**, or **unclear**, groups them into subscription candidates, and attempts only the unsubscribe actions the user explicitly confirms.

The UI operates on a **subscription candidate**, not a single message. Messages are classified individually, then grouped by `List-ID`, unsubscribe endpoint, or sender identity. Each candidate shows a representative message, frequency, date range, reason, evidence, and available unsubscribe method.

## Confirmed V1 decisions

| Topic | Decision |
|---|---|
| Mail source | One real Gmail account; no credential-free product demo. Synthetic mail remains test-only. |
| Default scan | Last 30 days, capped at 500 messages; user-adjustable within configured bounds. |
| Gmail access | Fetch the complete MIME message/body when needed for classification using `gmail.readonly`. Do not persist full bodies by default. |
| Application split | React/Vite/TypeScript frontend; FastAPI/Python backend. FastAPI serves the compiled frontend in production. |
| Model | OpenAI `gpt-5-mini`, called through a provider adapter and the Python Agents SDK/Responses API. |
| Agent role | Classify and explain only. It cannot unsubscribe, browse, send mail, or authorize actions. |
| Agent tools | At most one read-only local function tool to retrieve up to three related message samples, callable once. No MCP server is required in V1. |
| Unsubscribe methods | RFC 8058 HTTPS POST, `mailto:`, then a visible isolated Playwright browser flow. |
| Gmail send scope | Request `gmail.send` incrementally only when the user chooses a `mailto:` action. Show the exact message before confirmation. |
| Outcome vocabulary | `submitted`, `confirmed`, `needs_user`, and `failed` are distinct; HTTP 2xx or a loaded page alone is not confirmation. |

## V1 success criteria

- A new user can clone, configure Google OAuth and an OpenAI API key, run the app locally, connect a real Gmail account, and complete a bounded scan using the setup guide.
- The app reads complete Gmail message content where required to understand the email, normalizes and sanitizes it, and sends only the documented classification payload to OpenAI. The UI clearly discloses that selected email content is processed by OpenAI.
- OAuth starts with `gmail.readonly`. `gmail.send` is requested later only if the user elects to use `mailto:` unsubscribe; refresh tokens are stored in the OS credential store rather than SQLite.
- The default scan covers at most the last 30 days and 500 messages. Interrupted scans resume without duplicate records.
- Every candidate has a category, confidence, concise reason, evidence, grouping identity, and unsubscribe method. Low-confidence or conflicting results become **unclear**.
- Category sections are independently collapsible. Nothing is selected by default, hidden selections remain visible in category counts, and the exact action plan is shown before confirmation.
- RFC 8058 POST, `mailto:`, and browser flows use the method-specific retry rules below and record a durable result for each candidate.
- Automated tests cover MIME parsing, grouping, URL policy, state transitions, idempotency and retries; a versioned eval set measures classification precision/recall and abstention quality.

## Scope

### In scope

- One local user and one Gmail account.
- Real Gmail OAuth, bounded listing, full-message retrieval, MIME decoding, HTML-to-safe-text normalization, and header/body unsubscribe discovery.
- Hybrid classification: deterministic signals protect obvious transactional mail; `gpt-5-mini` produces a strict structured decision.
- Candidate grouping, collapsible review UI, manual corrections, explicit batch confirmation, progress, history, and redacted diagnostics.
- RFC 8058 HTTPS POST, incrementally authorized Gmail `mailto:` sending, and visible Playwright fallback with user takeover.
- Synthetic and scrubbed fixtures strictly for automated tests and evals, not as a substitute for the real-email V1 acceptance path.

### Non-goals for V1

- A credential-free demo, hosted multi-user service, background/scheduled cleanup, Outlook/IMAP, mobile app, or automatic unsubscribe without confirmation.
- Deleting, archiving, labeling, marking spam, or recursively processing confirmation emails.
- Bypassing CAPTCHA, login, MFA, paywalls, consent controls, or anti-bot protections.
- Reporting **confirmed** solely because a web page loaded or an endpoint returned HTTP 2xx. Those signals prove transport worked, not that the sender accepted the unsubscribe. Without explicit semantic evidence, record **submitted** or **needs_user**.

## Product and agent boundary

The model receives untrusted email content as data and returns only a schema-validated classification. Deterministic application code owns OAuth, parsing, grouping, URL validation, consent, side effects, retries, and state. The model has no unsubscribe, browser, network, mail-send, filesystem, or shell tool.

The final **Confirm unsubscribe** action is the irreversible boundary. For `mailto:`, confirmation includes recipient, subject, and body. For browser actions, confirmation explains that an isolated visible window will open and may pause for the user.

## User-visible browser flow

1. The candidate is marked **Website** and the confirmation screen shows the destination origin.
2. After confirmation, a visible Playwright window opens in a new isolated profile, never the user's normal browser profile.
3. Automation may follow only unsubscribe or preference-management controls and may make at most two pre-submission navigation attempts.
4. It pauses before ambiguity, login, CAPTCHA, MFA, cross-origin navigation, or any action unrelated to unsubscribing. The app shows **Take over**, **Resume**, and **Cancel**.
5. The final unsubscribe click is attempted once. It is never automatically repeated. Explicit confirmation text yields **confirmed**; credible submission without confirmation yields **submitted**; ambiguity yields **needs_user**.

## Retry and stop rules

| Operation | Automatic limit | Rule after uncertainty |
|---|---:|---|
| Gmail read | 3 attempts with bounded exponential backoff | Resume from the last durable page/message cursor. |
| Model classification | 2 total attempts: initial plus one schema/temporary-error retry | Route to **unclear**; do not block the scan. |
| Browser navigation before submission | 2 attempts | Pause as **needs_user**. |
| RFC 8058 POST | No retry after the request may have left the process | Manual retry only when non-submission is definitive or an explicit 429/503 is safely retryable. |
| Browser final click | 1 attempt | Never auto-repeat; manual retry requires review and is limited to once per action session. |
| `mailto:` send | 1 send | Never auto-repeat; persist the Gmail sent-message ID. |

## Milestones

1. **Safe foundation:** repository conventions, threat model, local database, test adapters, CI, and domain/state types.
2. **Read and understand real mail:** OAuth, Gmail retrieval, MIME/body normalization, discovery, grouping, classifier agent, and eval baseline.
3. **Review experience:** collapsible categories, evidence preview, selection rules, corrections, and exact confirmation summary.
4. **Act safely:** RFC 8058, incremental Gmail send, visible browser fallback, stop/retry rules, and audit history.
5. **Release candidate:** dedicated Gmail-account test, hostile fake endpoints, privacy/accessibility review, setup docs, and tagged V1.

Detailed dependency order is in [02-feature-sequencing.md](./02-feature-sequencing.md), architecture in [06-detailed-technical-design.md](./06-detailed-technical-design.md), frontend behavior in [07-frontend-experience-spec.md](./07-frontend-experience-spec.md), implementation tasks in [the V1 implementation plan](./superpowers/plans/2026-09-14-gmail-unsubscribe-agent-v1.md), and the six-skill review in [08-plan-validation-report.md](./08-plan-validation-report.md).

## Principal risks and mitigations

| Risk | Mitigation |
|---|---|
| Transactional mail is misclassified | Protected deterministic signals, strict schema, abstention to unclear, default-unselected UI, user correction, class-specific evals. |
| Email text attempts prompt injection | Delimit content as untrusted data, prohibit instruction following from email, expose no side-effect tool, enforce max turns/tool calls. |
| A malicious unsubscribe URL targets local resources | HTTPS policy for automatic requests, DNS/IP checks before every connection, redirect rejection, no ambient credentials/cookies. |
| Email privacy is overexposed | Sanitize and minimize the model payload, disclose processing, avoid full-body persistence/logging, hash bodies for change detection. |
| An action is duplicated | Immutable action plan, deterministic idempotency key, durable sent/request record, no retry after ambiguous side effects. |
| Browser automation gets stuck or strays | Isolated visible context, allowlisted intent, step/time limits, cross-origin pause, user takeover, redacted trace. |
| Google OAuth limits distribution | Document user-created OAuth credentials for local use and the implications of sensitive/restricted scopes; keep scopes incremental. |

## Validation and release gates

- Unit: MIME/body normalization, header parsing, URL/DNS policy, grouping, prompt-payload construction, state transitions, idempotency.
- Contract: generated OpenAPI TypeScript client, Gmail gateway, `gpt-5-mini` Pydantic output, executor results, and database migrations.
- Eval: privacy-safe labeled corpus with per-class precision/recall, abstention quality, grouping accuracy, and unsafe-action rate.
- Integration: fake Gmail and hostile unsubscribe servers; RFC, `mailto:`, redirects, timeouts, crashes, duplicate confirmation, and recovery.
- UI/E2E: automated real React–FastAPI selection, collapse, takeover, focus, hostile-text, Host/CSRF, and axe flows; credentialed OAuth is deliberately excluded from CI.
- Release: `make verify` must pass first. Then run safe `make smoke-real-read`, the separately acknowledged controlled executor smoke, a clean setup exercise, assistive-technology checks, and sensitive-data inspection.

## Remaining design questions

- What configurable retention period should apply to message metadata, classifications, and action history?
- What packaging path best delivers Python, the compiled Vite assets, and Playwright Chromium without obscuring the open-source development workflow?

## Source notes

Gmail listing returns message references first, then `messages.get` retrieves full message details ([Gmail message listing](https://developers.google.com/workspace/gmail/api/guides/list-messages)). Gmail scopes are separate for reading and sending ([Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)). `gpt-5-mini` supports the Responses API, function calling, and Structured Outputs ([model page](https://developers.openai.com/api/docs/models/gpt-5-mini)). The Python Agents SDK supports function tools, guardrails, tracing, and Pydantic-validated structured output ([Python Agents SDK](https://openai.github.io/openai-agents-python/)).
