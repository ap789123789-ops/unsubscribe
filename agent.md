# Gmail Unsubscribe Agent

## Project status

This repository is currently in the **planning/design phase**. The specifications are complete, but the `frontend/`, `backend/`, tests, and run scripts described below have not been implemented yet.

Do not claim the application runs until the implementation and credentialed smoke test exist and pass.

## What it does

This is a local-first, open-source application for reviewing and unsubscribing from Gmail mailing lists.

The V1 flow is:

1. Connect one real Gmail account using OAuth.
2. Scan a bounded set of messages (default: 30 days, maximum: 500).
3. Read and normalize complete email content when needed.
4. Classify each message as **marketing**, **non-marketing**, or **unclear** using deterministic rules and OpenAI `gpt-5-mini`.
5. Group messages into subscription candidates.
6. Let the user review collapsible categories, inspect evidence, correct results, and select candidates. Nothing is selected by default.
7. Show an immutable action plan for explicit confirmation.
8. Attempt unsubscribe through RFC 8058 HTTPS POST, `mailto:`, or a visible isolated Playwright browser.
9. Report **submitted**, **confirmed**, **needs_user**, or **failed** without treating transport success as proof of completion.

The model classifies and explains only. It cannot browse, send mail, unsubscribe, access the filesystem, or approve actions.

## Tech stack

### Frontend

- React, Vite, and TypeScript
- Generated TypeScript client from FastAPI OpenAPI
- Vitest and Testing Library for component tests
- Playwright Test for cross-stack E2E tests

### Backend

- Python 3.12 and `uv`
- FastAPI and Pydantic
- SQLAlchemy 2, Alembic, and SQLite
- OpenAI Agents SDK with `gpt-5-mini`
- Google Gmail API Python client
- Python `keyring` using macOS Keychain or Linux Secret Service
- Playwright Python with headed, isolated Chromium
- pytest for unit, API, integration, and agent-eval tests

### Runtime shape

The frontend is a static presentation tier. FastAPI owns domain logic, Gmail access, classification, persistence, and unsubscribe execution. In production, FastAPI serves the compiled Vite assets from `127.0.0.1`, so the app uses one long-running process and a same-origin UI/API boundary.

## How to run it

### Today

There is no runnable application yet. Review the planning set under `docs/`, starting with:

- `docs/01-v1-project-plan.md`
- `docs/06-detailed-technical-design.md`
- `docs/07-frontend-experience-spec.md`
- `docs/superpowers/plans/2026-09-14-gmail-unsubscribe-agent-v1.md`

### Planned development workflow

The first implementation task will add the actual setup commands and `Makefile`. The intended workflow is:

```bash
# Install backend dependencies
cd backend
uv sync

# Install frontend dependencies
cd ../frontend
npm install

# Install Playwright Chromium
uv run playwright install chromium

# Start FastAPI and the Vite development server
# Exact commands will be documented when Task 1 is implemented.
```

Required product credentials will include:

- a Google OAuth desktop client configured for the loopback callback;
- an OpenAI API key;
- a dedicated Gmail account for safe release testing.

OAuth begins with `gmail.readonly`. The app requests `gmail.send` only when the user explicitly chooses a `mailto:` unsubscribe action.

Do not add a credential-free product demo. Synthetic Gmail/OpenAI adapters are for automated tests only.

## Planned folder structure

```text
frontend/
  src/api/generated/       # generated from FastAPI OpenAPI; never hand-edit
  src/app/                 # routing and application shell
  src/features/            # setup, scan, review, confirmation, activity
  src/styles/              # tokens and global styles
  tests/components/
  tests/e2e/
backend/
  app/api/                 # thin FastAPI transport layer
  app/domain/              # models and action state machine
  app/persistence/         # SQLAlchemy repositories and migrations
  app/gmail/               # OAuth, message retrieval, send/reconciliation
  app/email_processing/    # MIME normalization and unsubscribe discovery
  app/classification/      # deterministic rules and bounded agent
  app/candidates/          # grouping and candidate revisions
  app/actions/             # immutable plans and execution coordination
  app/executors/           # RFC 8058, mailto, and browser methods
  app/security/            # secrets, URL policy, encryption, CSRF
  tests/                   # unit, API, integration, and eval suites
  alembic/
scripts/                   # OpenAPI generation and project utilities
docs/                      # product, architecture, UX, security, and plans
Makefile                   # planned common development commands
```

## Important implementation rules

- Fetch real Gmail messages for product acceptance; fixtures do not satisfy V1 success.
- Keep full email bodies in memory by default. Never persist or log bodies, OAuth tokens, signed URLs, cookies, or model payloads.
- Treat email text, model output, and sender websites as untrusted input.
- Keep side effects in deterministic Python services behind typed protocols.
- Require a current immutable plan digest and explicit user confirmation before execution.
- Never automatically repeat a possibly issued POST, email send, or final browser click.
- RFC 8058 and `mailto:` remain **submitted** in V1. Only explicit, validated browser-page evidence may become **confirmed**.
- Bind FastAPI to loopback and enforce Host, Origin, session, and CSRF checks on mutations.
- Test the real React–FastAPI–SQLite path; fake only third-party boundaries in CI.
- Follow red-green-refactor and commit each vertical task independently.

## What is coming next

Implementation follows the eight tasks in the V1 implementation plan:

1. Create the React/Vite and FastAPI shell plus generated OpenAPI client.
2. Add loopback security, configuration, SQLite persistence, and the action state machine.
3. Implement real Gmail OAuth, bounded scanning, complete-message retrieval, and resume.
4. Add MIME normalization, unsubscribe discovery, grouping, classifier agent, and evals.
5. Build the accessible review and confirmation experience.
6. Implement safe RFC 8058 and `mailto:` executors.
7. Add visible isolated Playwright execution and user takeover.
8. Add recovery, CI, documentation, accessibility/security checks, and the real credentialed release gate.

Two product decisions remain open: metadata/history retention defaults and the final macOS/Linux packaging approach.

## Source of truth

When documents disagree, use this order:

1. `docs/06-detailed-technical-design.md`
2. `docs/07-frontend-experience-spec.md`
3. `docs/01-v1-project-plan.md`
4. `docs/superpowers/plans/2026-09-14-gmail-unsubscribe-agent-v1.md`

Update the relevant design document before intentionally changing a confirmed architectural or safety decision.
