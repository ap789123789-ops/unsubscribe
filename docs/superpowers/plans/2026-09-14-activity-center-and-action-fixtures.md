# Activity Center and Action Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, global unsubscribe Activity Center with honest outcomes and state-specific repair controls, then validate RFC 8058, `mailto:`, and browser actions with controlled sample emails.

**Architecture:** Persist the immutable display identity needed by history on each action, project the latest durable action event through a read-only FastAPI activity endpoint, and render one chronological React ledger. Existing browser intervention remains the browser repair path; the only new retry paths are one reviewed RFC retry after an explicit 429/503 and a `mailto:` retry proven not to have started because Gmail send authorization was absent.

**Tech Stack:** Python 3.12+/FastAPI/SQLAlchemy/Alembic/Pydantic, TypeScript/React/Vite/openapi-fetch, pytest, Vitest Testing Library, Playwright.

**Spec:** `docs/07-frontend-experience-spec.md` and `docs/06-detailed-technical-design.md`

## Global Constraints

- No unsubscribe side effect occurs before the user confirms the immutable plan.
- `submitted` never appears as confirmed success.
- Never repeat a request whose first submission may have left the app.
- Signed URLs remain encrypted at rest and are redacted to an origin/recipient in APIs and UI.
- Browser repair preserves the guarded session and never repeats a final click.
- Automated tests set `APP_ENABLE_EXTERNAL_SERVICES=false` and mock only Gmail/OpenAI/sender boundaries.
- Existing user changes in `frontend/package-lock.json` and `env` remain untouched.

---

## File map

- Create `backend/alembic/versions/20260914_0004_action_activity_metadata.py`: add immutable sender, subject, and redacted-target action columns.
- Modify `backend/app/domain/models.py`: carry those safe display fields in `ActionRecord`.
- Modify `backend/app/persistence/models.py`: map new activity columns.
- Modify `backend/app/persistence/repositories.py`: list global/plan activity, return latest evidence, and durably consume one retry allowance.
- Create `backend/app/api/activity.py`: expose `GET /api/actions` and guarded `POST /api/actions/{id}/retry`.
- Modify `backend/app/actions/coordinator.py`: build display metadata and execute only policy-eligible reviewed retries.
- Modify `backend/app/main.py`: wire the activity router and URL policy into the coordinator.
- Modify `frontend/src/api/client.ts`: consume generated activity APIs.
- Replace `frontend/src/features/activity/ActivityPage.tsx`: global/plan ledger, filters, outcome evidence, and repair dialogs.
- Modify `frontend/src/app/router.tsx` and `frontend/src/app/AppShell.tsx`: add `/activity` and primary navigation.
- Modify `frontend/src/styles/tokens.css`: responsive ledger and filter styles using existing tokens.
- Modify `backend/tests/e2e_app.py`: connected Gmail-send fixture and controlled outcomes for all three methods.
- Add API/component/E2E tests at the agreed public seams.

## Design plan

- **Palette:** keep Paper `#F6F7F2`, Ink `#17212B`, Rule `#C9CEC7`, Marketing orange `#A64B00`, Unclear violet `#7656A7`, and Safe blue `#246B8E`.
- **Type:** retain self-hosted IBM Plex Sans; use tabular figures for timestamps and counts.
- **Layout:** a dispatch ledger rather than cards. Status rails and text carry meaning; filters are a compact toolbar.

```text
Activity                                      2 need attention
All  Needs attention  Working  Sent  Confirmed  Not submitted
────────────────────────────────────────────────────────────────
Morning Brief       One-click request     Request sent      Sep 14
This week…          example.com           Processing unverified
────────────────────────────────────────────────────────────────
Community           Website                Your help needed  Sep 14
September update    community.example      Login required    Review blocker
```

- **Self-critique:** summary cards would make this look like a generic analytics dashboard and would separate counts from the work. The ledger keeps identity, evidence, status, and remediation in one scan path, matching the product's mailroom metaphor.

### Task 1: Durable activity projection

**Files:** migration, domain model, ORM model, repository, `backend/tests/integration/test_persistence.py`

**Interfaces:**
- Produces `ActivityRecord(action, evidence_code, safe_detail)`.
- Produces `ActionRepository.list_activity(plan_id: str | None = None) -> tuple[ActivityRecord, ...]` ordered newest first.
- Produces `ActionRepository.consume_retry(action_id) -> ActionRecord` with an atomic maximum of one.

- [ ] **Step 1: Write a failing repository test** that confirms two plans are returned newest first with sender, subject, redacted target, and latest event evidence, while a plan filter returns only matching rows.
- [ ] **Step 2: Run** `cd backend && APP_ENABLE_EXTERNAL_SERVICES=false uv run pytest tests/integration/test_persistence.py -q`; expect missing activity projection/columns.
- [ ] **Step 3: Add migration and model fields.** New action fields are non-null with safe legacy defaults:

```python
display_sender: Mapped[str] = mapped_column(String(500), default="Unknown sender")
display_subject: Mapped[str] = mapped_column(Text, default="(no subject)")
target_display: Mapped[str] = mapped_column(String(500), default="Unknown destination")
```

- [ ] **Step 4: Implement the latest-event projection** using the greatest `action_events.stream_sequence` per action; never decrypt payloads for list reads.
- [ ] **Step 5: Run the focused test** and confirm it passes.
- [ ] **Step 6: Commit** the durable projection.

### Task 2: Activity API and policy-limited repair

**Files:** coordinator, repository, activity router, main wiring, `backend/tests/api/test_activity.py`, `backend/tests/integration/test_action_coordinator.py`

**Interfaces:**
- Produces `GET /api/actions?plan_id=<optional>&limit=100`.
- Produces `POST /api/actions/{action_id}/retry` with CSRF/Origin protection.
- Produces `ExecutionCoordinator.review_and_retry(action_id: str) -> ActionRecord`.

- [ ] **Step 1: Write a failing API test** for a global activity item containing `id`, `plan_id`, `sender`, `subject`, `target_display`, `method`, `state`, `evidence_code`, `safe_detail`, `updated_at`, and `browser_session_id`.
- [ ] **Step 2: Run** `cd backend && APP_ENABLE_EXTERNAL_SERVICES=false uv run pytest tests/api/test_activity.py -q`; expect a 404.
- [ ] **Step 3: Implement the read endpoint** with `limit` constrained to 1–500 and optional plan filtering.
- [ ] **Step 4: Write failing coordinator tests** for these independent known outcomes:

```text
failed + http_429/http_503 + retry_count 0 -> one reviewed RFC retry
needs_user + gmail_send_authorization_required + retry_count 0 -> one mailto retry
submitted/confirmed/uncertain-mail/final-click-issued/second retry -> reject without side effect
```

- [ ] **Step 5: Implement retry eligibility.** The endpoint is itself the renewed user confirmation. It consumes the retry allowance before the outbound call, revalidates an RFC target, reconstructs only the exact encrypted mail draft, and records every state transition.
- [ ] **Step 6: Run focused API/coordinator tests** and confirm both pass.
- [ ] **Step 7: Regenerate OpenAPI and TypeScript** with `make openapi`.
- [ ] **Step 8: Commit** the API and repair policy.

### Task 3: Global Activity Center

**Files:** API client, ActivityPage, router, AppShell, tokens CSS, `frontend/tests/components/activity.test.tsx`

**Interfaces:**
- Consumes generated `ActivityActionResponse` and `ActivityActionListResponse`.
- Keeps `/activity/:planId` as a filtered compatibility route and adds `/activity` globally.

- [ ] **Step 1: Write a failing component test** with RFC submitted, browser needs-user, mailto authorization-required, and failed non-retryable rows. Assert identity/evidence, filters, and that only eligible rows expose a repair action.
- [ ] **Step 2: Run** `cd frontend && npm test -- --run tests/components/activity.test.tsx`; expect the global ledger behavior to be absent.
- [ ] **Step 3: Implement API client functions** `listActions(planId?)` and `retryAction(actionId)`.
- [ ] **Step 4: Implement the ledger** with semantic filter buttons, an accessible list, safe exact evidence, localized timestamps, empty/error states, and browser intervention dialog.
- [ ] **Step 5: Implement repair UX:** browser blocker controls; Gmail authorization followed by explicit email retry; and a confirmation dialog before one eligible RFC retry. No control is rendered for submitted, confirmed, or uncertain actions.
- [ ] **Step 6: Add the Activity nav item and responsive styles.** On narrow screens each ledger row becomes a two-column label/value stack without changing reading order.
- [ ] **Step 7: Run component tests, ESLint, and TypeScript** and confirm all pass.
- [ ] **Step 8: Commit** the Activity Center.

### Task 4: Controlled sample-email action flows

**Files:** `backend/tests/e2e_app.py`, `frontend/tests/e2e/activity-center.spec.ts`, existing action-flow specs as failures reveal.

**Interfaces:** Browser-visible review → confirmation → execution → global activity, with deterministic fake Gmail and sender boundaries.

- [ ] **Step 1: Add connected read/send OAuth fixture state** so the browser can execute, not merely preview, the `mailto:` sample without contacting Google.
- [ ] **Step 2: Add three uniquely named sample candidates** representing RFC accepted, mailto accepted, and browser login-required results.
- [ ] **Step 3: Write one failing Playwright journey** that selects all three samples, confirms the exact destinations, executes once, opens global Activity, and observes submitted/submitted/needs-user outcomes attached to the correct senders.
- [ ] **Step 4: Exercise browser repair** through Review blocker → Take over → Resume and verify only that row becomes confirmed.
- [ ] **Step 5: Assert safety:** no signed token appears, submitted rows never say confirmed, and no unexpected page or console error occurs.
- [ ] **Step 6: Run** `APP_ENABLE_EXTERNAL_SERVICES=false npm --prefix frontend run test:e2e -- --reporter=list`; diagnose and fix product failures rather than weakening locators.
- [ ] **Step 7: Repeat the critical new test five times** using `--grep @activity --repeat-each=5`.
- [ ] **Step 8: Commit** the controlled action fixtures and E2E coverage.

### Task 5: Documentation, review, and release gate

**Files:** `README.md`, `agent.md`, `docs/06-detailed-technical-design.md`, `docs/07-frontend-experience-spec.md`

- [ ] **Step 1: Document** global history, exact statuses, repair eligibility, and the controlled fixture boundary.
- [ ] **Step 2: Verify `agent.md` remains under 200 lines.**
- [ ] **Step 3: Request an independent differential review** against this plan; fix every Critical and Important finding.
- [ ] **Step 4: Run `make verify` fresh** and require exit code 0.
- [ ] **Step 5: Inspect the staged diff** and exclude `frontend/package-lock.json`, `env`, credentials, SQLite files, `.local`, and browser profiles.
- [ ] **Step 6: Commit and push `main`**, then restart the local backend and verify `/api/health` returns 200.

## Self-review

- Spec coverage: global navigation/history, durable identity/evidence, honest outcome labels, browser repair, limited safe retry, all three methods, responsive/accessibility checks, and external-service isolation each map to a task.
- Placeholder scan: the plan contains no deferred implementation markers.
- Type consistency: `ActivityRecord`, `ActivityActionResponse`, `listActions`, and `review_and_retry` keep the same names and roles across backend, generated client, UI, and tests.
