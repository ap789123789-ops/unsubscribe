# Contributing

## Development setup

Install Python 3.12/3.13, `uv`, Node.js 22+, npm, and Chromium support. Then run:

```bash
make setup
cd backend && uv run playwright install chromium && cd ..
npm --prefix frontend exec playwright install chromium
make verify
```

Real credentials are not needed for automated development. Never commit `.env`, Google client files,
OAuth tokens, inbox content, signed unsubscribe URLs, browser profiles, or copied databases.

## Change workflow

1. Read `agent.md` and the relevant design section.
2. Add a behavior test at an agreed public seam and confirm it fails for the intended reason.
3. Implement the smallest vertical slice; fake only external Google/OpenAI/DNS/time/sender boundaries.
4. Run focused tests, then `make verify`.
5. If a FastAPI contract changed, run `make openapi` and commit both generated artifacts.
6. Explain privacy, consent, retry, and state-machine effects in the pull request.

Do not hand-edit `frontend/src/api/generated/schema.ts`. Do not weaken URL validation, CSRF/Host
checks, encrypted payload storage, model boundaries, or one-side-effect rules merely to simplify a
test. New executor states must be legal in `backend/app/domain/state_machine.py` and covered by tests.

## Test layers

- Python unit: pure parsing, classification, policy, state, and plan behavior.
- Python API/integration: real FastAPI, SQLite/migrations, recovery, executors, and hostile fixtures.
- Agent evals: recorded runner and versioned examples; no live model in CI.
- React component: user-visible state and accessibility behavior.
- Playwright E2E: real React–FastAPI requests; external services only are faked.
- Credentialed smoke: safe real Gmail/OpenAI read/classification first; controlled destructive
  endpoint checks separately, never CI.

## Style and review

Python uses Ruff and mypy; TypeScript uses ESLint and strict `tsc`. Prefer explicit typed protocols,
small transport routes, evidence-based status text, accessible names, and event-driven Playwright
assertions. Security-sensitive changes need a differential review covering callers, tests, history,
and concrete abuse cases.
