# Gmail Unsubscribe Agent V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local application that reads real Gmail messages, classifies and groups subscription candidates, supports deliberate review, and safely executes confirmed RFC 8058, `mailto:`, or visible browser unsubscribe actions.

**Architecture:** React/Vite/TypeScript is a static presentation tier. FastAPI/Python owns the OpenAPI contract, Gmail, classification agent, domain/state machine, SQLite, and Playwright. FastAPI serves the compiled frontend in production; external services are behind typed Python protocols.

**Tech Stack:** Python 3.12, `uv`, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite, Python `keyring`, OpenAI Agents SDK, `gpt-5-mini`, Google Gmail API client, Playwright Python, pytest, React, Vite, TypeScript, Vitest, Testing Library, Playwright Test, OpenAPI TypeScript.

**Spec:** `docs/06-detailed-technical-design.md`; UX contract: `docs/07-frontend-experience-spec.md`

## Global Constraints

- Product acceptance requires one real Gmail account and OpenAI credentials; synthetic mail is test-only.
- Default scan is the last 30 days and at most 500 messages.
- Full bodies are processed in memory and are not persisted or logged by default.
- OAuth starts with `gmail.readonly`; request `gmail.send` only for a user-selected `mailto:` action.
- The model is `gpt-5-mini`, returns strict Pydantic output, has one read-only sample tool callable once, and has no side-effect capability.
- No unsubscribe executor runs without a matching immutable plan digest and explicit user confirmation.
- A transport success alone is never `confirmed`; use `submitted`, `needs_user`, or `failed` as specified.
- A possibly issued POST, email send, or final browser click is never automatically repeated.
- FastAPI binds to `127.0.0.1`; mutations require allowed Host/Origin and CSRF validation.

---

## Planned file map

```text
frontend/
  package.json
  vite.config.ts
  src/api/generated/              # generated only
  src/app/router.tsx
  src/features/setup/
  src/features/scan/
  src/features/review/
  src/features/confirmation/
  src/features/activity/
  src/styles/tokens.css
  tests/components/
  tests/e2e/
backend/
  pyproject.toml
  app/main.py
  app/api/
  app/domain/
  app/persistence/
  app/gmail/
  app/email_processing/
  app/classification/
  app/candidates/
  app/actions/
  app/executors/
  app/security/
  alembic/
  tests/unit/
  tests/api/
  tests/integration/
  tests/evals/
scripts/
  export_openapi.py
Makefile
```

Files are grouped by capability. FastAPI route modules depend on use-case services; use-case services depend on protocols; only adapter modules import Google, OpenAI, SQLAlchemy, HTTP, keyring, or Playwright clients.

### Task 1: Same-origin application shell and generated API contract

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/api/health.py`, `backend/app/api/schemas.py`
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/api/client.ts`
- Create: `scripts/export_openapi.py`, `Makefile`
- Test: `backend/tests/api/test_health.py`, `frontend/tests/e2e/shell.spec.ts`

**Interfaces:**
- Produces: `GET /api/health -> HealthResponse`; `/openapi.json`; generated `frontend/src/api/generated/`; production static fallback excluding `/api`, `/auth`, `/events`.
- Consumes: none.

- [ ] **Step 1: Write the failing backend contract test**

```python
def test_health_contract(client):
    response = client.get("/api/health", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "api_version": "v1"}
```

- [ ] **Step 2: Run it and confirm red**

Run: `cd backend && uv run pytest tests/api/test_health.py -q`
Expected: FAIL because `app.main` or `/api/health` does not exist.

- [ ] **Step 3: Implement the minimal FastAPI contract and static mount**

```python
class HealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    api_version: Literal["v1"] = "v1"

@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
```

Configure `TrustedHostMiddleware` for `127.0.0.1`, `localhost`, and test host. Mount `frontend/dist/assets` and return its `index.html` only for non-API routes.

- [ ] **Step 4: Add OpenAPI generation and frontend contract check**

Run: `uv run python scripts/export_openapi.py && npm --prefix frontend run generate:api`
Expected: `frontend/src/api/generated/` contains typed `HealthResponse` and no handwritten DTO.

- [ ] **Step 5: Build and exercise the real frontend/backend seam**

Run: `npm --prefix frontend test && npm --prefix frontend run build && cd backend && uv run pytest tests/api/test_health.py -q`
Expected: all commands exit 0; the E2E shell requests the real FastAPI health route rather than intercepting it.

- [ ] **Step 6: Commit**

```bash
git add backend frontend scripts Makefile
git commit -m "build: add Vite and FastAPI application shell"
```

### Task 2: Loopback security, configuration, persistence, and action state

**Files:**
- Create: `backend/app/config.py`, `backend/app/api/security.py`, `backend/app/security/secrets.py`
- Create: `backend/app/domain/models.py`, `backend/app/domain/state_machine.py`
- Create: `backend/app/persistence/database.py`, `backend/app/persistence/models.py`, `backend/alembic/`
- Test: `backend/tests/api/test_loopback_security.py`, `backend/tests/unit/test_state_machine.py`, `backend/tests/integration/test_migrations.py`

**Interfaces:**
- Produces: `AppSettings`; `require_local_mutation(request)`; Pydantic action unions; `ActionStateMachine.transition(action, event)`; SQLAlchemy repositories and Alembic head.
- Consumes: Task 1 FastAPI application.

- [ ] **Step 1: Define the public invariants as failing tests**

```python
@pytest.mark.parametrize("event,expected", [
    (ActionEvent.USER_CONFIRMED, ActionStatus.CONFIRMED_BY_USER),
    (ActionEvent.EXPLICIT_ACCEPTANCE, ActionStatus.CONFIRMED),
    (ActionEvent.TRANSPORT_ONLY, ActionStatus.SUBMITTED),
    (ActionEvent.UNKNOWN_AFTER_SIDE_EFFECT, ActionStatus.NEEDS_USER),
])
def test_action_transitions(action_factory, event, expected):
    action = action_factory.valid_for(event)
    assert ActionStateMachine().transition(action, event).status is expected
```

Add API cases rejecting an unexpected Host, absent/mismatched Origin, and absent CSRF token with 400/403.

- [ ] **Step 2: Run focused tests and confirm red**

Run: `cd backend && uv run pytest tests/unit/test_state_machine.py tests/api/test_loopback_security.py -q`
Expected: FAIL because the security dependency and transition table do not exist.

- [ ] **Step 3: Implement a table-driven state machine and local mutation dependency**

```python
ALLOWED_TRANSITIONS: dict[tuple[ActionStatus, ActionEvent], ActionStatus] = {
    (ActionStatus.SELECTED, ActionEvent.USER_CONFIRMED): ActionStatus.CONFIRMED_BY_USER,
    (ActionStatus.EXECUTING, ActionEvent.EXPLICIT_ACCEPTANCE): ActionStatus.CONFIRMED,
    (ActionStatus.EXECUTING, ActionEvent.TRANSPORT_ONLY): ActionStatus.SUBMITTED,
    (ActionStatus.EXECUTING, ActionEvent.UNKNOWN_AFTER_SIDE_EFFECT): ActionStatus.NEEDS_USER,
}
```

Generate a random per-launch CSRF value, bind it to an HttpOnly SameSite=Strict session cookie, require the matching `X-CSRF-Token` header, and reject mutations whose `Origin` is not the configured loopback origin. Use Python `keyring` only when its selected backend is macOS Keychain or Linux Secret Service; reject `keyrings.alt`, plaintext/file, fail, and null backends. Scanning/review may continue without a keyring, but OAuth persistence and actions fail closed with an explicit setup error.

- [ ] **Step 4: Add the complete V1 migration and repository round trip**

Create the tables specified in design section 7, including unique Gmail ID, versioned candidate, unique action idempotency key, append-only action events, and encrypted action payload column. Test migration from an empty SQLite file and repository retrieval only through public repository methods.

- [ ] **Step 5: Verify**

Run: `cd backend && uv run alembic upgrade head && uv run pytest tests/unit/test_state_machine.py tests/api/test_loopback_security.py tests/integration/test_migrations.py -q`
Expected: all pass; invalid transitions raise `InvalidTransition` without a database write.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/alembic backend/tests
git commit -m "feat: add secure local state foundation"
```

### Task 3: Real Gmail OAuth, bounded listing, complete-message retrieval, and resume

**Files:**
- Create: `backend/app/gmail/protocol.py`, `backend/app/gmail/google_gateway.py`, `backend/app/gmail/oauth.py`
- Create: `backend/app/api/auth.py`, `backend/app/api/scans.py`, `backend/app/scans/orchestrator.py`
- Test: `backend/tests/unit/test_scan_bounds.py`, `backend/tests/api/test_oauth_callback.py`, `backend/tests/integration/test_scan_resume.py`

**Interfaces:**
- Produces: `GmailGateway.create_authorization_url`, `exchange_authorization_code`, `list_message_refs`, `get_complete_message`, `revoke`; `POST /api/scans`; scan SSE events.
- Consumes: settings, security dependency, repositories, state types.

- [ ] **Step 1: Write failing boundary tests**

```python
async def test_default_scan_is_bounded(scan_service, fake_gmail):
    scan = await scan_service.start(ScanRequest())
    assert fake_gmail.last_query.after_days == 30
    assert fake_gmail.total_requested <= 500
    assert scan.max_messages == 500
```

Test OAuth state mismatch, missing PKCE verifier, token storage through the credential-store protocol, three-read retry limit, checkpoint after each page, duplicate message IDs, revoke, and restart from the stored page/message cursor.

- [ ] **Step 2: Confirm red**

Run: `cd backend && uv run pytest tests/unit/test_scan_bounds.py tests/api/test_oauth_callback.py tests/integration/test_scan_resume.py -q`
Expected: FAIL because Gmail and scan protocols are absent.

- [ ] **Step 3: Implement the protocol and fake first**

```python
class GmailGateway(Protocol):
    async def list_message_refs(self, query: GmailListQuery) -> MessageRefPage: ...
    async def get_complete_message(self, gmail_id: str) -> RawGmailMessage: ...
```

Inject gateway, credential store, clock, retry policy, and repositories into `ScanOrchestrator`. Persist the checkpoint before publishing its SSE event.

- [ ] **Step 4: Implement Google OAuth/read adapter**

Use PKCE plus state/nonce, `gmail.readonly`, the official Python client, `messages.list` followed by `messages.get(format="full")`, and the checked Python `keyring` adapter. Never store tokens in SQLite or frontend storage.

- [ ] **Step 5: Verify automated and real seams**

Run: `cd backend && uv run pytest tests/unit/test_scan_bounds.py tests/api/test_oauth_callback.py tests/integration/test_scan_resume.py -q`
Expected: all automated tests pass with fake Google boundaries.

Manual release check: run the opt-in `uv run pytest -m real_gmail tests/smoke/test_real_gmail_read.py -q` against a dedicated account and verify at least one complete MIME body is returned. Never run this in CI.

- [ ] **Step 6: Commit**

```bash
git add backend/app/gmail backend/app/scans backend/app/api backend/tests
git commit -m "feat: connect and scan a bounded Gmail mailbox"
```

### Task 4: Normalize email, discover methods, classify with Python agent, and group candidates

**Files:**
- Create: `backend/app/email_processing/mime.py`, `sanitizer.py`, `unsubscribe.py`
- Create: `backend/app/classification/schemas.py`, `prompt.py`, `agent.py`, `rules.py`
- Create: `backend/app/candidates/grouper.py`
- Test: `backend/tests/unit/test_mime.py`, `test_sanitizer.py`, `test_unsubscribe.py`, `test_grouping.py`
- Test: `backend/tests/evals/cases.jsonl`, `backend/tests/evals/test_classifier_eval.py`

**Interfaces:**
- Produces: `EmailNormalizer.normalize`; `UnsubscribeDiscovery.discover`; `ClassifierModel.classify`; `CandidateGrouper.rebuild`.
- Consumes: complete Gmail messages, message/classification repositories.

- [ ] **Step 1: Agree and encode the behavioral seams**

Tests call only the four public interfaces above. External OpenAI calls are replaced at `ClassifierModel`; internal rules, prompt construction, repositories, and sample lookup are not mocked.

- [ ] **Step 2: Write the first failing corpus tests**

```python
def test_html_message_becomes_safe_text(normalizer, malicious_html_message):
    email = normalizer.normalize(malicious_html_message)
    assert "Save 40%" in email.sanitized_body_text
    assert "<script" not in email.sanitized_body_text
    assert "tracking.example/pixel" not in email.sanitized_body_text
    assert email.full_body_persistable is False
```

Add independent expected literals for multipart selection, charsets, folded headers, `mailto:` query decoding, list identity, transactional protection, mixed-content abstention, prompt injection, one-tool-call limit, schema failure, and grouping priority. Cover the 10 MiB message threshold, 2 MiB decoded-text ceiling, and deterministic 20,000-character model-body allocation (12,000 opening, 4,000 footer, 4,000 high-signal windows).

- [ ] **Step 3: Confirm red, then implement one vertical behavior at a time**

Run after every new case: `cd backend && uv run pytest tests/unit/test_mime.py tests/unit/test_sanitizer.py tests/unit/test_unsubscribe.py tests/unit/test_grouping.py -q`
Expected sequence: each new test fails for the intended reason, then passes after the minimal behavior is implemented.

- [ ] **Step 4: Implement the bounded agent**

```python
classification_agent = Agent(
    name="Email purpose classifier",
    model="gpt-5-mini",
    instructions=CLASSIFICATION_SYSTEM_PROMPT,
    output_type=ClassificationOutput,
    tools=[get_related_message_samples],
)

result = await Runner.run(classification_agent, payload, max_turns=2, context=context)
return enforce_postconditions(result.final_output, expected_message_id=input.message_id)
```

The tool reads at most three already-fetched sanitized samples, rejects a second invocation, and has no Gmail/network/executor access. One transient/schema retry is outside the two-turn run; unresolved output becomes `unclear`.

- [ ] **Step 5: Run eval and privacy gates**

Run: `cd backend && uv run pytest tests/unit tests/evals/test_classifier_eval.py -q`
Expected: schema validity 100%; unauthorized tool calls 0; protected transactional cases not marketing; low-confidence/mixed/injection cases unclear; no full body in database/log capture.

- [ ] **Step 6: Commit**

```bash
git add backend/app/email_processing backend/app/classification backend/app/candidates backend/tests
git commit -m "feat: classify and group subscription candidates"
```

### Task 5: Build the accessible review and confirmation experience

**Files:**
- Create: `backend/app/api/candidates.py`, `backend/app/api/action_plans.py`
- Create: `frontend/src/app/router.tsx`, `frontend/src/styles/tokens.css`
- Create: `frontend/src/features/setup/`, `scan/`, `review/`, `confirmation/`, `activity/`
- Test: `backend/tests/api/test_candidates.py`, `test_action_plans.py`
- Test: `frontend/tests/components/review.test.tsx`, `confirmation.test.tsx`, `frontend/tests/e2e/review.spec.ts`

**Interfaces:**
- Produces: candidate list/correction APIs; immutable plan preview; routes and interactions in UX spec.
- Consumes: generated API client, candidate repository, plan service.

- [ ] **Step 1: Write failing API behavior tests**

Test pagination, category filtering, correction-created revision, stale-revision rejection, endpoint/method dedupe, encrypted method payload, plan digest, and absence of full bodies/signed query values in responses.

- [ ] **Step 2: Write failing component behavior tests**

```tsx
it('discloses selected items while Marketing is collapsed', async () => {
  render(<ReviewPage candidates={candidates} />)
  await user.click(screen.getByRole('checkbox', { name: /weekly offers/i }))
  await user.click(screen.getByRole('button', { name: /marketing/i }))
  expect(screen.getByRole('button', { name: /marketing.*1 selected/i })).toHaveAttribute('aria-expanded', 'false')
})
```

Cover nothing-preselected, visible-only selection, evidence-dialog focus restoration, correction clearing stale selection, status text not relying on color, exact `mailto:` preview, and stale-plan copy.

- [ ] **Step 3: Confirm red**

Run: `cd backend && uv run pytest tests/api/test_candidates.py tests/api/test_action_plans.py -q && npm --prefix frontend test`
Expected: tests fail because endpoints/components are absent.

- [ ] **Step 4: Implement the API and React slices using generated types**

Use semantic table/list markup, real buttons for accordion headers, `aria-expanded`, named regions, a dialog for evidence/confirmation on narrow screens, polite live regions for progress, and exact copy from `docs/07-frontend-experience-spec.md`. Do not add a generic dashboard card grid.

- [ ] **Step 5: Verify component, accessibility, and cross-stack flow**

Run: `npm --prefix frontend test && npm --prefix frontend run test:e2e -- --grep @review`
Expected: all pass against real FastAPI/temp SQLite; Google/OpenAI are adapter fakes; axe has zero serious/critical violations.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api backend/tests/api frontend
git commit -m "feat: add subscription review and confirmation"
```

### Task 6: Execute RFC 8058 and `mailto:` actions safely

**Files:**
- Create: `backend/app/security/url_policy.py`, `backend/app/security/payload_crypto.py`
- Create: `backend/app/actions/planner.py`, `coordinator.py`
- Create: `backend/app/executors/rfc8058.py`, `mailto.py`
- Extend: `backend/app/gmail/google_gateway.py`
- Test: `backend/tests/unit/test_url_policy.py`, `test_action_planner.py`
- Test: `backend/tests/integration/test_rfc_executor.py`, `test_mailto_executor.py`

**Interfaces:**
- Produces: plan/execution policies; RFC and mail executors; incremental-send OAuth; reconciliation by deterministic RFC `Message-ID`.
- Consumes: confirmed plan, state machine, credential store, Gmail protocol, encrypted payload repository.

- [ ] **Step 1: Write failing adversarial policy tests**

```python
@pytest.mark.parametrize("url", [
    "http://example.com/u",
    "https://user:secret@example.com/u",
    "https://127.0.0.1/u",
    "https://169.254.169.254/latest/meta-data",
])
async def test_automatic_request_rejects_unsafe_target(policy, url):
    with pytest.raises(UnsafeTarget):
        await policy.validate_at_plan_time(url)
```

Add DNS-rebinding, all-A/AAAA-record validation, redirect, timeout, oversized response, duplicate confirmation, crash-after-write, explicit 429/503, and no-send-scope cases.

- [ ] **Step 2: Confirm red**

Run: `cd backend && uv run pytest tests/unit/test_url_policy.py tests/unit/test_action_planner.py tests/integration/test_rfc_executor.py tests/integration/test_mailto_executor.py -q`
Expected: FAIL because policies/executors are absent.

- [ ] **Step 3: Implement RFC 8058 and encrypted target handling**

Revalidate DNS immediately before connection; POST exactly `List-Unsubscribe=One-Click`; omit ambient cookies/auth; disable redirects; cap connect/read time and body bytes. Record a successfully issued RFC request as `submitted`, never `confirmed`. Encrypt the exact target/method payload with the AES-256-GCM envelope specified in the design using a supported-keyring-backed key; expose only origin and redacted recipient in API/logs.

- [ ] **Step 4: Implement incremental send and reconciliation**

Generate an opaque deterministic `Message-ID` from the action UUID, persist `executing` plus that ID before Gmail send, show the exact recipient/subject/body before confirmation, and on uncertainty query Sent mail using `rfc822msgid:`. A located Gmail ID yields `submitted`; absence yields `needs_user`, not an automatic resend.

- [ ] **Step 5: Verify**

Run: `cd backend && uv run pytest tests/unit/test_url_policy.py tests/unit/test_action_planner.py tests/integration/test_rfc_executor.py tests/integration/test_mailto_executor.py -q`
Expected: all pass; request counters prove each side effect occurs at most once per action attempt.

- [ ] **Step 6: Commit**

```bash
git add backend/app/security backend/app/actions backend/app/executors backend/app/gmail backend/tests
git commit -m "feat: add approved RFC and mailto unsubscribe actions"
```

### Task 7: Add visible isolated Playwright execution and user takeover

**Files:**
- Create: `backend/app/executors/browser.py`, `backend/app/executors/browser_policy.py`
- Create: `backend/app/api/browser_sessions.py`
- Extend: `frontend/src/features/activity/`
- Test: `backend/tests/integration/test_browser_executor.py`
- Test: `frontend/tests/e2e/browser-intervention.spec.ts`

**Interfaces:**
- Produces: headed browser executor; `POST /api/browser-sessions/{id}/resume|cancel`; intervention SSE events.
- Consumes: validated encrypted action, URL policy, state machine, activity UI.

- [ ] **Step 1: Write failing behavior and attack tests**

Use local fixture sites to cover allowlisted English acceptance phrases, negated/error phrases, non-English/unmatched results, transport-only result, login, MFA/CAPTCHA marker, ambiguous unsubscribe-all choice, popup, cross-origin navigation, final-click disconnect, private-IP iframe/image/fetch, service-worker attempt, download, closed window, and two-navigation limit.

- [ ] **Step 2: Confirm red**

Run: `cd backend && uv run pytest tests/integration/test_browser_executor.py -q`
Expected: FAIL because the browser executor does not exist.

- [ ] **Step 3: Implement browser isolation and request policy**

Launch headed Chromium with a unique temporary profile. Block service workers, downloads, permissions, extensions, and default credential reuse. Intercept every top-level and subresource request; resolve and reject non-public targets. Pause before popup/cross-origin navigation and before ambiguous controls. Allow two pre-submission navigations and one automatic final click.

- [ ] **Step 4: Implement intervention UX**

Expose **Take over in browser**, **Resume automation**, and **Stop this action** only when their transition is legal. Move dialog focus to the blocker heading, use a polite status live region, and restore focus to the activity row on close.

- [ ] **Step 5: Verify repeatedly**

Run: `cd backend && uv run pytest tests/integration/test_browser_executor.py -q && npm --prefix frontend run test:e2e -- --grep @browser --repeat-each=5`
Expected: all five runs pass without fixed sleeps; request logs show zero private-network requests and at most one final click.

- [ ] **Step 6: Commit**

```bash
git add backend/app/executors backend/app/api backend/tests frontend/src/features/activity frontend/tests
git commit -m "feat: add visible browser unsubscribe fallback"
```

### Task 8: Recovery, verification matrix, documentation, and release gate

**Files:**
- Create: `backend/app/recovery.py`, `backend/tests/integration/test_recovery.py`
- Create: `frontend/tests/e2e/critical-flow.spec.ts`, `frontend/tests/e2e/security.spec.ts`, `frontend/tests/e2e/accessibility.spec.ts`
- Create: `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `.github/workflows/ci.yml`
- Modify: `docs/01-v1-project-plan.md`, `docs/06-detailed-technical-design.md`

**Interfaces:**
- Produces: startup recovery; contributor setup; CI/release evidence.
- Consumes: every prior public seam.

- [ ] **Step 1: Write failing recovery scenarios**

Test scan restart from checkpoint, `executing` RFC/browser becoming `needs_user`, `mailto:` reconciliation by deterministic Message-ID, terminal actions remaining terminal, expired browser profile cleanup, and SSE replay from the last event ID.

- [ ] **Step 2: Implement recovery before accepting API traffic**

Run migrations, reconcile durable mail receipts, transition unknown side effects to `needs_user`, resume read-only jobs, remove expired profiles, and only then report `/api/health` as ready.

- [ ] **Step 3: Add layered CI**

CI order: Python lint/typecheck/unit → migrations/API/integration → agent eval with recorded fake runner → frontend lint/typecheck/component → frontend build → generated-client diff check → cross-stack Playwright security/accessibility/critical flows. Real Gmail and live OpenAI remain explicit local release checks.

- [ ] **Step 4: Run the full automated gate**

Run: `make verify`
Expected: formatter/linter/typechecker/tests/build/evals/client-drift checks all exit 0; test summary has zero failures and zero serious/critical axe violations.

- [ ] **Step 5: Run the credentialed release gate**

Run: `make smoke-real`
Expected: dedicated Gmail connects; at least one complete body is classified by `gpt-5-mini`; a controlled RFC, mailto, and browser case each reaches the expected honest terminal state. The command requires explicit environment opt-in and never runs in CI.

- [ ] **Step 6: Perform manual UX/security checks**

Complete keyboard-only review, VoiceOver or NVDA pass, forced-colors/reduced-motion pass, disconnect/delete-data exercise, browser takeover, and log/database inspection proving no OAuth token, full body, cookie, or unredacted signed URL is present.

- [ ] **Step 7: Commit**

```bash
git add backend frontend README.md SECURITY.md CONTRIBUTING.md .github docs
git commit -m "chore: add V1 recovery and release gates"
```

## Plan self-review

- **Spec coverage:** Tasks 1–8 cover the two-language runtime, same-origin serving, OpenAPI contract, real Gmail/body access, classifier prompt/tool/output, review UX, three executors, state/retry semantics, recovery, privacy, security, accessibility, evals, and release.
- **Pre-agreed test seams:** FastAPI HTTP/SSE surface; scan/classification/grouping/action use-case services; Gmail/OpenAI/clock/DNS/credential-store/executor protocols; React component behavior; complete browser-visible flow.
- **Mocking boundary:** tests never mock React-to-FastAPI or use-case internals. CI fakes only Google, OpenAI, DNS/time where controlled inputs are required, and sender-owned endpoints; release smoke tests use real Gmail/OpenAI.
- **Dependency order:** every task consumes only interfaces produced earlier; executors follow URL policy, state machine, immutable plan, and UI confirmation.
- **Placeholder scan:** the plan contains no unresolved implementation marker; remaining product decisions are explicitly outside implementation readiness in the design document.
