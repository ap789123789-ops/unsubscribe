---
title: Gmail Unsubscribe Agent — Use Cases and Edge Cases
status: proposed
last_updated: 2026-09-14
owners: maintainers
---

# Use cases and edge cases

## Primary use cases

### UC1 — Connect real Gmail and scan

The user configures Google OAuth and an OpenAI API key, grants `gmail.readonly`, connects one Gmail account, and scans the last 30 days/up to 500 messages by default. The app fetches complete messages as needed, normalizes their bodies, reports progress, and safely resumes an interrupted scan.

**Acceptance:** the product has no credential-free demo path; full message content is not persisted or logged by default; the UI discloses that a sanitized classification payload is sent to OpenAI.

### UC2 — Review recommendations

Grouped candidates appear in independently collapsible **Marketing**, **Non-marketing**, and **Unclear** sections. Each row shows sender/list, representative subject, frequency, confidence/reason/evidence, and method. The user may correct a category.

**Acceptance:** nothing is selected by default; collapsed headers reveal hidden selection counts; corrections override the model locally and are never uploaded as training data without separate opt-in.

### UC3 — Confirm and run a mixed batch

The user selects candidates, reviews the exact list and method for each, and confirms one immutable snapshot. The app runs with bounded concurrency and shows `confirmed`, `submitted`, `needs_user`, or `failed` per candidate.

**Acceptance:** a rescan/regroup invalidates stale confirmation; two candidates resolving to the same action collapse into one disclosed action; restart cannot duplicate a possibly completed side effect.

### UC4 — Send a `mailto:` unsubscribe

When a header supplies `mailto:`, the app asks for incremental `gmail.send` permission, builds the required recipient/subject/body, displays that exact message, and sends it once after confirmation.

**Acceptance:** the sent Gmail message ID is stored before reporting submission; permission denial returns to review; the app never automatically resends or acts on a confirmation reply.

### UC5 — Complete a website unsubscribe

The app shows the destination origin, then opens a visible isolated Playwright profile. It may navigate twice before submission and interact only with unsubscribe/preferences controls. It pauses for ambiguity, login, MFA, CAPTCHA, or cross-origin movement and provides **Take over**, **Resume**, and **Cancel**.

**Acceptance:** the final submission control is clicked at most once automatically. A loaded page or HTTP 2xx is not enough for **confirmed**; explicit acceptance text is required, otherwise use **submitted** or **needs_user**.

### UC6 — Resume or retry

After a crash or network failure, the user sees durable scan/action history. Gmail reads may resume; irreversible actions whose outcome is unknown do not auto-retry. A qualifying manual retry requires review and is limited to one in the current action session.

## Edge-case catalog

### Gmail, body processing, and identity

- OAuth denial, expired/revoked token, incremental-send denial, quota exhaustion, pagination interruption, duplicate Gmail IDs, and mailbox mutation during scan.
- Multipart/alternative, nested MIME, charset and transfer encodings, attachments, inline images, forwarded/quoted history, enormous bodies, image-only messages, S/MIME/encrypted content, malformed MIME, and empty bodies.
- HTML scripts/styles/tracking pixels, hidden text, hostile markup, unsafe URLs, and body content that instructs the model or claims to be a system message.
- Same brand has marketing, receipts, security alerts, and product notifications; different brands share an email-service provider; sender/list identity changes over time.
- Aliases, plus addressing, delegated/Workspace accounts, forwarded mail, spoofed display names, lookalike domains, and failed authentication evidence.

### Classification

- Transactional mail contains recommendations; marketing mail contains account/order notices; community, job, political, nonprofit, event, survey, creator, and social mail depends on user preference.
- Non-English text, sparse text, image-only offers, conflicting headers/body, or related samples with different purposes.
- Model timeout, rate limit, refusal, invalid schema, low confidence, contradiction with protected rules, or an attempted prompt injection. Retry once only when safe, then classify **unclear**.
- The optional related-sample tool finds zero or many messages, returns stale samples, or is requested twice. Return at most three and reject a second call.

### Unsubscribe discovery and execution

- Multiple folded/encoded `List-Unsubscribe` values; `mailto:` with encoded subject/body; invalid addresses; HTTPS URL without valid `List-Unsubscribe-Post`; body contains preference, privacy, login, or tracker links.
- Relative, shortened, expired, already-used, or recipient-signed URLs; email-service-provider domain differs from the sender.
- HTTP/private/link-local/reserved targets, nonstandard ports, embedded credentials, DNS rebinding, origin-changing redirect, TLS failure, timeout, 429/503, 2xx error page, and connection loss after submission.
- `mailto:` send succeeds but local response is lost. Use the durable Gmail sent-message ID; never guess and resend.
- Preference page contains unsubscribe-one vs unsubscribe-all, reason survey, dark patterns, auto-subscribe, unrelated destructive controls, download, popup, consent banner, or browser-extension prompt.
- Sender requires login/MFA/CAPTCHA or an emailed confirmation link. Pause as **needs_user**; never bypass or recursively inspect new mail.

### Batch, state, and UX

- Category collapses with selected rows; visible-only “select all”; candidate changes after selection; duplicate action endpoint; cancellation with queued/in-flight work; partial success; machine sleep; app/browser crash.
- Endpoint returned 2xx or page loaded without semantic confirmation. Record transport evidence, not a false **confirmed** state.
- Sender continues mail after submission. Preserve history and advise verification after the sender's processing period rather than retrying automatically.
- Empty scan, all unclear, slow scan, missing OpenAI key, model outage, narrow screen, keyboard-only and screen-reader use, shared machine, and local backup exposure.

## Initial eval slices

Maintain a versioned synthetic/scrubbed corpus covering promotions, receipts, security alerts, newsletters, mixed and non-English mail, malformed MIME, image-only/no-unsubscribe cases, malicious prompt text, and deceptive endpoints. Report per-class precision/recall, confusion matrix, abstention quality, grouping accuracy, schema-failure rate, unsafe-action rate, and tool-call-limit violations. Marketing precision and zero unauthorized actions matter more than maximum coverage.
