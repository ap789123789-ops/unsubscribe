---
title: Gmail Unsubscribe Agent — Feature and Technical Overview
status: proposed
last_updated: 2026-09-14
owners: maintainers
length_note: intentionally kept to approximately half a page
---

# Feature overview

The local app connects to one real Gmail account and scans the last 30 days/up to 500 messages by default. It reads complete message bodies where needed, finds unsubscribe evidence, classifies each message as **marketing**, **non-marketing**, or **unclear**, and groups related messages into mailing-list candidates. Independently collapsible categories show counts, representative mail, frequency, confidence, reasons, evidence, and method. Nothing is preselected. The user reviews an exact action plan, confirms once, and sees `confirmed`, `submitted`, `needs_user`, or `failed` per item. V1 requires Gmail and OpenAI credentials; synthetic data is test-only.

# Technical design overview

Use a React/Vite/TypeScript frontend and a FastAPI/Python backend. FastAPI owns Gmail, the domain/state machine, SQLite via SQLAlchemy/Alembic, the OpenAI Python Agents SDK backed by `gpt-5-mini`, and Playwright Python; it serves the compiled frontend in production. Pydantic generates OpenAPI, which generates the TypeScript client. Gmail begins with `gmail.readonly`; complete MIME messages are decoded and sanitized in memory, while full bodies are not stored by default. The classifier returns a Pydantic-validated object and may call one read-only related-sample function once; it has no MCP or side-effect tool.

Deterministic code owns grouping, URL safety, consent, retries, and execution. An action state machine permits `discovered → reviewed → selected → confirmed_by_user → executing → confirmed | submitted | needs_user | failed`. Executors prefer RFC 8058 HTTPS POST, support `mailto:` after incremental `gmail.send` authorization and exact draft review, then use a visible isolated browser with bounded navigation and user takeover. Final POST, send, or click is never automatically repeated after an uncertain outcome. A page load or HTTP 2xx proves transport only, not unsubscribe confirmation. See the [detailed design](./06-detailed-technical-design.md).
