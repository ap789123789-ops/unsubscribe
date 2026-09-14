---
title: Gmail Unsubscribe Agent — Feature Sequence
status: proposed
last_updated: 2026-09-14
owners: maintainers
---

# Feature sequence

Build vertical slices. Synthetic adapters support automated testing, but every release increment is ultimately exercised with a dedicated real Gmail account.

| Order | Feature slice | Depends on | Exit check |
|---:|---|---|---|
| 0 | Repository foundation: React/Vite/TypeScript frontend, FastAPI/Python backend, `uv` and npm workspaces, lint/typecheck/test, `.env.example`, safe logging | — | Fresh clone builds the frontend, starts FastAPI, and passes both toolchains. |
| 1 | API contract and same-origin shell: Pydantic schemas, OpenAPI generation, generated TypeScript client, Vite dev proxy, FastAPI static serving, loopback/Host/Origin/CSRF policy | 0 | Contract drift check passes; production starts as one FastAPI process on `127.0.0.1`. |
| 2 | Domain and state model: SQLAlchemy/Alembic persistence, messages, candidates, action plans, results, test-only boundary fakes | 1 | pytest proves migrations, public use-case seams, transitions, and idempotency invariants. |
| 3 | Real Gmail read connection: Python Google client, PKCE OAuth, OS keyring, revoke/disconnect, default 30 days/500 | 1–2 | Dedicated Gmail account connects, paginates, resumes, and disconnects with `gmail.readonly`. |
| 4 | Complete-message ingestion: MIME decode, plain/HTML normalization, header/body discovery, privacy-safe persistence | 3 | Corpus covers multipart, encodings, quoted history, malformed and large messages; real bodies render safely. |
| 5 | Candidate grouping: `List-ID` → normalized unsubscribe endpoint → sender fallback | 4 | Campaigns dedupe without merging unrelated lists from the same brand. |
| 6 | Python classifier agent: deterministic protections, sanitized input, `gpt-5-mini`, Pydantic output, one bounded read-only sample tool, evals | 4–5 | Per-class targets pass; low confidence, conflicts, model errors, and prompt injection route safely. |
| 7 | Review UI: accessible collapsible categories, counts, filters, safe preview, reasons/evidence, correction, visible-only bulk selection | 5–6 | Component tests prove all visual states; nothing preselected; hidden selections remain disclosed. |
| 8 | Immutable action plan: method resolution, encrypted execution payload, URL policy, exact review, candidate revisions, idempotency | 7 | Any candidate change invalidates confirmation; no executor is reachable without current consent. |
| 9 | RFC 8058 executor: validated HTTPS POST, no ambient credentials/redirects, concurrency cap, durable result | 8 | Hostile server verifies request shape, DNS checks, no duplicate, and no local-network access. |
| 10 | `mailto:` executor: incremental `gmail.send`, exact preview, deterministic `Message-ID`, reconciliation, one send | 8 | Crash after send is reconciled from Gmail; the app never silently resends. |
| 11 | Python Playwright executor: headed isolated context, all-request network policy, blocked service workers/downloads, two navigations, one final click, takeover | 8–9 | Test sites cover success, preferences, login, CAPTCHA, cross-origin/subresource SSRF, broken page, and timeout. |
| 12 | Results and recovery: SSE events, per-item state, submitted/confirmed distinction, eligible retry, history, diagnostics | 9–11 | Partial failures and restart recovery are understandable without duplicating uncertain actions. |
| 13 | OSS release hardening: setup guide, architecture/UX/security reviews, eval guide, accessibility, dependency/license checks | all | A new contributor configures credentials and completes a real Gmail scan from the README alone. |

## Delivery increments

### A — trustworthy recommendations

Slices 0–7. A credentialed user connects real Gmail, scans, classifies, groups, and reviews. Side effects remain disabled while classifier quality and privacy are evaluated.

### B — deterministic actions

Slices 8–10 and 12. Enable RFC 8058 and `mailto:` behind a development flag until fake-server and dedicated-account tests pass. `gmail.send` is requested only when first needed.

### C — browser coverage and public V1

Slices 11 and 13. Browser automation remains a fallback and always runs visibly with a user takeover path.

## Requirement traceability

| Requirement | Slices |
|---|---|
| Access and read real Gmail bodies | 3–4 |
| Classify with `gpt-5-mini` | 6 |
| Review/collapse/select categories | 7–8 |
| RFC 8058 unsubscribe | 9 |
| `mailto:` unsubscribe | 10 |
| Visible website flow and bounded retry | 11–12 |
| Publish for others to use | 0–1, 13 |

## Sequencing rules

- Keep Gmail, model, clock/DNS, and executor implementations behind Python protocols; fake implementations exist only for tests.
- Treat FastAPI's OpenAPI document as the frontend/backend contract and fail CI when the generated TypeScript client is stale.
- Build the URL policy, consent boundary, state machine, and idempotency record before any executor.
- Do not tune prompts on raw production mail. Convert opted-in, scrubbed failures into eval cases and compare against a frozen baseline.
- Use one classification agent and one deterministic application orchestrator. Add agents or MCP only after traces/evals demonstrate a specific need.
