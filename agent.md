# Gmail Unsubscribe Agent

## What this project does

This is a local-first Gmail subscription review and unsubscribe application. It connects to one
real Gmail account, reads complete message bodies when needed, classifies mail as **marketing**,
**non-marketing**, or **unclear** with deterministic rules plus OpenAI `gpt-5-mini`, and groups
messages into subscription candidates.

The user reviews collapsible categories, selects nothing by default, sees exact destinations or
`mailto:` content, and explicitly confirms an immutable action plan. Python then attempts RFC 8058,
Gmail `mailto:`, or a visible isolated Playwright flow. The model can classify and explain; it has
no unsubscribe, browser, mail-send, approval, filesystem, or arbitrary Gmail tools.

Statuses are intentionally honest: **submitted** means a request left the app, **confirmed** needs
explicit browser-page acceptance evidence, **needs_user** means automation paused, and **failed**
means no accepted submission was established.

## Current status

The eight planned V1 implementation slices are present, with automated unit, API, integration,
agent-eval, component, E2E, security, and accessibility gates. This is not a credential-free demo.
V1 acceptance still requires `make smoke-real-read` with a dedicated Gmail account and OpenAI key.
The separate destructive `make smoke-real` gate requires controlled unsubscribe fixtures, followed
by the documented manual assistive-technology/security checklist.

## Tech stack

- Frontend: React 19, Vite, TypeScript, generated OpenAPI client, Vitest, Testing Library, Playwright.
- Backend: Python 3.12/3.13, FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite, `uv`.
- Agent: OpenAI Agents SDK using `gpt-5-mini`, strict structured output, one bounded read-only tool.
- Integrations: Gmail API OAuth; Python Playwright Chromium; macOS Keychain/Linux Secret Service.

FastAPI owns all domain logic and serves the built frontend from loopback in the production-shaped
local flow. React never receives Gmail OAuth tokens, raw signed unsubscribe targets, or full bodies.

## Setup and run

Prerequisites: `uv`, Node.js 22+ with npm, Chromium support, an OpenAI API key, and a Google OAuth
desktop client with Gmail API enabled and loopback callback `http://127.0.0.1:8000/auth/google/callback`.

```bash
cp .env.example .env
# Set OPENAI_API_KEY and APP_GOOGLE_CLIENT_SECRETS_FILE in .env.
make setup
cd backend && uv run playwright install chromium && cd ..
npm --prefix frontend exec playwright install chromium
make build
make dev-backend
```

Open `http://127.0.0.1:8000`, connect Gmail, scan a bounded range, and review the results. OAuth
starts with `gmail.readonly`; `gmail.send` is requested only when a selected action needs `mailto:`.

Development servers can be split with `make dev-backend` and `make dev-frontend`. Common checks:

```bash
make openapi     # regenerate the checked API contract/client after backend route changes
make lint
make typecheck
make test
make verify      # complete automated release gate, including cross-stack Playwright
```

`make smoke-real-read` safely retrieves and classifies one real message without unsubscribing.
`make smoke-real` is destructive: it submits controlled real requests and requires the explicit
acknowledgement and fixture variables documented in `README.md`.

## Folder structure

```text
backend/
  app/api/                 # FastAPI routes, local session/CSRF, SSE activity
  app/domain/              # Pydantic records and action state machine
  app/persistence/         # SQLAlchemy repositories and startup migrations
  app/gmail/               # OAuth, complete-message reads, send/reconciliation
  app/email_processing/    # hostile MIME normalization and unsubscribe discovery
  app/classification/      # rules, bounded classifier agent, output validation
  app/candidates/          # grouping and user-correction revisions
  app/actions/             # immutable plans and execution coordination
  app/executors/           # RFC 8058, mailto, guarded visible browser
  app/security/            # credential store, URL policy, encrypted payloads
  app/scan/                # bounded reads and durable checkpoints
  app/recovery.py          # restart reconciliation before readiness
  tests/                   # unit, API, integration, eval, and E2E fixture app
  alembic/                 # versioned SQLite migrations
frontend/
  src/api/generated/       # generated from FastAPI; never hand-edit
  src/features/            # setup, scan, review, confirmation, activity, settings
  tests/components/        # React behavior tests
  tests/e2e/               # real React–FastAPI browser flows
scripts/                   # OpenAPI drift check and explicit real smoke gate
docs/                      # product, architecture, UX, risk, and implementation plans
.github/workflows/ci.yml   # locked, least-privilege automated gate
```

## Implementation rules

- Product acceptance always uses real Gmail and complete body retrieval; test fakes never count.
- Keep bodies in memory by default. Never log/persist bodies, tokens, cookies, model payloads, or
  signed query strings.
- Treat email, model output, and sender sites as hostile. Keep side effects in typed Python services.
- Require the current plan digest and explicit user confirmation before any side effect.
- Never automatically repeat a possibly issued POST, email, or final browser click.
- Bind loopback, enforce Host/Origin/session/CSRF, and retain browser network guards during takeover.
- Test the real React–FastAPI path; fake only Google, OpenAI, DNS/time, and sender-owned boundaries.
- Use red → green at public seams, update OpenAPI artifacts, and run `make verify` before claiming done.

## What comes next

After the real credentialed/manual V1 release gate passes, the next decisions are:

1. Choose metadata/history retention and delete-data defaults.
2. Choose macOS/Linux packaging and signed distribution.
3. Add more model/provider options only after the `gpt-5-mini` baseline is measured.
4. Consider other mail providers after Gmail V1 reliability and safety evidence is established.

## Source of truth

When documents disagree: `docs/06-detailed-technical-design.md`, then
`docs/07-frontend-experience-spec.md`, then `docs/01-v1-project-plan.md`, then the implementation
plan. Update the relevant design document before intentionally changing a confirmed safety decision.
