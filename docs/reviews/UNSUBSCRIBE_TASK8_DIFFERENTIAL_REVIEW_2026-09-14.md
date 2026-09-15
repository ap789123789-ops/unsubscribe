---
title: Task 8 Differential Security Review
status: automated-gate-passed-live-gates-pending
reviewed_base: 32f99ac
last_updated: 2026-09-14
---

# Executive summary

This focused review compared the Task 8 working tree with `32f99ac` (the completed browser-fallback
milestone). The first pass found two critical and seven important weaknesses. They were corrected
before commit and now have regression coverage. No unresolved critical, high, or medium code finding
remains in the reviewed scope; release approval is still conditional on the real Gmail/OpenAI smoke
and the documented manual checks.

| Severity | Open | Remediated during review |
|---|---:|---:|
| Critical | 0 | 2 |
| High/important | 0 | 7 |
| Low | 0 | 3 |

**Overall code risk:** medium because this feature crosses OAuth, external-network, browser, encrypted
persistence, and irreversible-action boundaries.  
**Recommendation:** approve the code milestone; do not call V1 release-certified until the live and
manual gates are recorded.

**Metrics:** 73 changed files; all high-risk paths and direct dependencies reviewed; 0 untested
high-risk fixes; automated gate passed with 41 unit, 53 API/integration, 4 eval, 5 component, and 8
cross-stack E2E tests.

## What changed

Task 8 adds startup migration/recovery, replayable durable action events, security headers, release
documentation and CI, production-shaped E2E tests, and credentialed smoke utilities. The review also
hardened existing action, OAuth, and outbound-network boundaries discovered while tracing the new
recovery and release paths.

| Area | Risk | Review result |
|---|---|---|
| Confirmation and action idempotency | Critical | Semantic action fingerprint prevents a fresh equivalent plan from repeating a prior side effect. |
| RFC/browser outbound networking | Critical | Final public address is pinned into HTTPX/Chromium; redirects and cross-origin browser requests remain blocked. |
| Startup recovery and migrations | High | Recovery runs without Gmail credentials, resolves action states before scans, and rejects unknown legacy schemas. |
| OAuth credentials | High | Supported keyrings are checked by concrete backend type; disconnect attempts Google revocation and always clears locally. |
| SSE replay | Medium | Integer database sequence replaces timestamp/UUID ordering and is validated per plan. |
| Cross-stack/release tests | Medium | E2E now uses real planner/coordinator/repository; external providers remain the only fakes. |

## Findings and remediations

### Critical: equivalent plans could repeat an unchanged side effect

**Location:** `backend/app/actions/coordinator.py:44` and `:122`  
**Blast radius:** 12 call/test sites for action state persistence; public confirmation API reachable
after local session/CSRF validation.  
**Historical context:** uniqueness for both plan digests and action idempotency keys originated in
`480d17c`; an intermediate Task 8 migration would have removed plan-digest uniqueness.

An attacker-controlled sender could present the same target again, and a user could create a fresh
plan UUID after an uncertain request. Plan-scoped idempotency would permit a second POST/send/click.
The coordinator now derives a semantic fingerprint from the reviewed candidate revision, method,
target, and exact mail body, checks it before confirmation, uses it for the deterministic action ID,
and preserves both database uniqueness constraints. An integration test proves a fresh equivalent
plan receives `action_already_attempted` rather than invoking an executor.

### Critical: DNS validation did not bind the subsequent connection

**Location:** `backend/app/executors/rfc8058.py:44`, `backend/app/executors/browser.py:37`  
**Blast radius:** all RFC 8058 and browser unsubscribe targets; low caller count but direct hostile
network exposure.

A malicious hostname could resolve publicly during validation and privately during the actual
client/browser lookup. RFC execution now connects to the validated address while preserving the
original Host/SNI and verifies the peer. Chromium receives a host-resolver mapping for the final
validated address, while request interception rejects unsafe or cross-origin traffic. Integration
coverage includes an unresolvable hostname that succeeds only through the pin and fixtures proving
Host/SNI/address propagation.

### Important: incomplete recovery could strand or repeat work

**Location:** `backend/app/recovery.py:54`  
**Blast radius:** seven migration call sites, three rehydration sites, and all actions present at
restart.

Database migration/recovery previously depended on Google/keyring setup, scans could run before
action reconciliation, one deleted Gmail message could abort all rehydration, and actions interrupted
between confirmation and execution could remain stranded. Startup now always migrates and recovers;
it reconciles `executing` actions first, safely returns unstarted confirmed actions to review,
continues rehydrating after individual message failures, and leaves durable checkpoints for retry.

### Important: replay cursor was not monotonic

**Location:** `backend/app/persistence/repositories.py:77`  
**Blast radius:** two event-stream call sites.

Timestamp/UUID ordering could skip or reorder events. `action_events.stream_sequence` is now an
autoincrementing cursor, migrated for existing rows and validated against the requested plan. The API
test deliberately moves a later event timestamp backward and still observes correct replay order.

### Important: credential and schema assumptions failed open

**Locations:** `backend/app/security/secrets.py:8`, `backend/app/persistence/database.py:42`,
`backend/app/gmail/oauth.py:93`.

Backend-name substring checks could be spoofed and unknown unversioned schemas could be stamped as a
known revision. The code now accepts only concrete macOS Keychain/Linux Secret Service classes and
fingerprints supported legacy schemas before stamping. Disconnect attempts Google's token-revocation
endpoint, suppresses token-bearing provider errors, and clears the local token/scopes in `finally`.

### Important: release tests over-mocked internal behavior

**Location:** `backend/tests/e2e_app.py:214`.

The prior E2E fixture bypassed the real plan/coordinator/repository behavior. It now migrates a real
temporary SQLite database and uses the production action services; only Gmail/OpenAI/DNS/sender
boundaries remain controlled. The safe real smoke separately verifies an expected Gmail profile,
complete-message retrieval, and one structured `gpt-5-mini` classification without side effects.

## Test coverage and blast radius

| High-impact function | Search matches including definition/tests | Coverage |
|---|---:|---|
| `create_app` | 15 | health/recovery, Host/CSRF, route and E2E tests |
| `set_state` | 12 | transition, persistence, recovery, API and E2E tests |
| `run_migrations` | 7 | fresh, two legacy shapes, preservation, and unknown-shape tests |
| `rehydrate` | 3 | restart, individual deletion/failure, continuation tests |
| `list_events` | 2 | plan-bound monotonic replay API test |
| `disconnect` | 6 | revoke success/failure and local-clear API/unit tests |

No changed high-risk production function lacks a focused regression test. The live Gmail/OpenAI test
and manual assistive-technology/security checks are intentionally outside CI and remain release
evidence gaps, not untested code paths.

## Historical context

The repository is young and contains no CVE/security-fix lineage. `git log -S` and blame found one
relevant invariant: commit `480d17c` introduced unique plan digests and action idempotency keys. The
review caught and reversed their accidental weakening before this Task 8 commit. No previously removed
vulnerable pattern was reintroduced.

## Remaining release gates

- [x] Fresh full `make verify` with zero failures.
- [ ] Safe `make smoke-real-read` using the expected real Gmail account and OpenAI API key.
- [ ] Separately acknowledged executor smoke against controlled endpoints owned by the releaser.
- [ ] Keyboard plus VoiceOver/NVDA, takeover, disconnect, and local database/log inspection.
- [ ] Clean-clone setup on the intended macOS/Linux distribution targets.

## Methodology and limitations

**Strategy:** focused review for a medium repository, with complete high-risk coverage and one-hop
dependency tracing. Techniques included base-to-working-tree diff analysis, git history/blame,
quantitative caller searches, test-seam inspection, and concrete attacker modeling for duplicate
effects, DNS rebinding, crash windows, cursor replay, credential fallback, and legacy migration.

Dependencies themselves were not audited, no live provider request was made during this code review,
and manual assistive-technology behavior was not assessed here. Confidence is high for the reviewed
application paths and medium for release readiness until the remaining gates pass.
