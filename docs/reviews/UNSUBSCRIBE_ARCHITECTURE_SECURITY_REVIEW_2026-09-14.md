# Gmail Unsubscribe Agent architecture security review

## Executive summary

| Severity | Open findings | Design controls added |
|---|---:|---:|
| Critical | 0 | 0 |
| High | 0 | 4 |
| Medium | 3 | 1 |
| Low | 1 | 0 |

**Overall inherent risk:** High  
**Residual design risk:** Medium  
**Recommendation:** Conditional approval for implementation. Do not enable unsubscribe executors until their adversarial tests pass.

The planned system reads private email and initiates external side effects, so its inherent risk remains high even with a narrow agent. The design now addresses four high-risk paths: hostile websites reaching private networks, cross-site access to a loopback API, duplicate `mailto:` sends after an uncertain response, and persisted signed unsubscribe-token exposure.

## Scope and limitations

- Reviewed all planning artifacts under `docs/`, emphasizing [the technical design](../06-detailed-technical-design.md) and [implementation plan](../superpowers/plans/2026-09-14-gmail-unsubscribe-agent-v1.md).
- This workspace is greenfield and contains no application code, Git baseline, call graph, test suite, or coverage data. Git blame, code diff, caller counts, regression history, and proof-of-concept exploitation are therefore unavailable.
- This is an adapted architecture review, not the code-level differential assurance the `differential-review` skill normally provides. Every control remains unverified until implementation.
- Confidence is high that the principal trust boundaries are represented, medium that the proposed controls will be sufficient in code, and zero regarding implementation correctness.

## What changed in this review

| Area | Risk | Design result |
|---|---|---|
| Stack boundary | Medium | React/Vite is presentation-only; FastAPI owns all backend/domain behavior; OpenAPI generates frontend types ([design lines 40–50](../06-detailed-technical-design.md)). |
| Loopback web security | High | Bind to `127.0.0.1`, strict Host/Origin/CSRF, production CORS disabled, same-origin static serving ([design line 90](../06-detailed-technical-design.md)). |
| Browser SSRF | High | Apply public-network validation to every top-level and subresource request, block service workers, retain policy during takeover ([design lines 455–456](../06-detailed-technical-design.md)). |
| Ambiguous mail send | High | Use a deterministic RFC `Message-ID` and reconcile Sent mail before any retry ([design lines 445–448](../06-detailed-technical-design.md)). |
| Sensitive action target | High | Encrypt exact method payload with an authenticated versioned envelope and fail closed without the key ([design line 458](../06-detailed-technical-design.md)). |
| Testing boundary | Medium | Test real React→FastAPI→SQLite behavior; fake only Google/OpenAI/sender boundaries in CI ([design lines 469–475](../06-detailed-technical-design.md)). |

## Adversarial analysis of controlled high-risk paths

### Hostile unsubscribe page attempts private-network access

**Attacker:** sender controlling the unsubscribe document and its scripts/subresources.  
**Entry point:** confirmed website action handled by the browser executor.  
**Attack:** the public page loads an image, iframe, fetch, service worker, redirect, or DNS-rebound hostname resolving to loopback, link-local, or RFC1918 space. This could read or mutate local services if only the initial navigation were checked.  
**Planned control:** revalidate every A/AAAA result before connection, intercept all page/subresource requests, block service workers/downloads/permissions, pause cross-origin movement, and retain the policy during takeover ([technical design lines 455–456](../06-detailed-technical-design.md)). Task 7 requires fixture attacks for private-IP iframe/image/fetch, service workers, popups, and cross-origin navigation ([implementation plan lines 426–445](../superpowers/plans/2026-09-14-gmail-unsubscribe-agent-v1.md)).  
**Residual risk:** browser protocol gaps, non-HTTP schemes, DNS race behavior, or an interception path missed by the chosen Playwright APIs.  
**Gate:** no browser executor release until the hostile-site suite proves zero private-network requests.

### Malicious website invokes the local API through the user's browser

**Attacker:** any remote website the user visits.  
**Entry point:** mutation routes on the loopback FastAPI server.  
**Attack:** cross-site form/fetch, DNS rebinding, or guessed localhost port attempts to start a scan, create/confirm a plan, retry an action, or delete data.  
**Planned control:** loopback-only binding, allowlisted Host, checked Origin, per-launch session/CSRF values, SameSite/HttpOnly cookie, disabled production CORS, and no wildcard cross-origin access ([technical design lines 90 and 457](../06-detailed-technical-design.md)). Task 2 requires explicit negative API cases before state work proceeds.  
**Residual risk:** malware or another process already running as the same OS user remains out of scope and must be stated to users.  
**Gate:** mutation tests must fail closed for missing or mismatched Host, Origin, cookie, and CSRF token.

### Gmail accepts an unsubscribe email but the response is lost

**Attacker/failure source:** network/process failure after Gmail accepts a send.  
**Entry point:** `mailto:` executor.  
**Attack:** recovery treats the action as failed and sends the same unsubscribe message again, possibly triggering multiple workflows or confusing the sender.  
**Planned control:** persist `executing` and an opaque deterministic RFC `Message-ID` before send; reconcile Gmail Sent mail by `rfc822msgid:`; absence remains `needs_user` rather than causing an automatic resend ([technical design line 445](../06-detailed-technical-design.md); [implementation plan lines 397–404](../superpowers/plans/2026-09-14-gmail-unsubscribe-agent-v1.md)).  
**Residual risk:** Gmail search/indexing delay can produce temporary absence.  
**Gate:** recovery tests must simulate acceptance followed by local connection loss and prove the external send counter remains one.

### Local database or backup exposes signed unsubscribe tokens

**Attacker:** person/process obtaining the SQLite database or an unprotected backup but not the OS credential store.  
**Entry point:** stored immutable action payload.  
**Attack:** signed URL query tokens or encoded email details are recovered and replayed or correlated.  
**Planned control:** AES-256-GCM versioned envelope with unique nonce and associated action/schema data; key stored separately in OS credentials; UI/logs expose only redacted origin/recipient; execution fails closed when the key is unavailable ([technical design line 458](../06-detailed-technical-design.md)).  
**Residual risk:** a same-user compromise can access both database and keyring; that is outside V1's declared threat model.  
**Gate:** tests must prove tampering fails authentication and database/log snapshots contain no plaintext target.

## Open findings

### Medium: Credential-store availability and packaging remain unverified

The design now selects Python `keyring`, accepts only macOS Keychain or Linux Secret Service, and fails closed rather than falling back to insecure storage. The remaining risk is whether clean supported machines reliably expose those backends and whether recovery copy is understandable. A missing key must not lead to silent action-payload regeneration or weaker file storage.

**Required before completing Task 2:** record and test supported backends, headless behavior, deletion semantics, and the exact user message when storage is unavailable.

### Medium: Semantic confirmation allowlist is designed but unvalidated

The design now limits automatic **confirmed** to a versioned English browser-page allowlist after negative/error patterns are excluded; RFC and mail always remain **submitted**. The residual risk is false positive matching against deceptive or unrelated page text.

**Required before enabling the browser executor:** validate the conservative allowlist against explicit success, unrelated text, “could not unsubscribe,” “unsubscribe link expired,” non-English, and adversarial mixed-text pages. Preserve the redacted matched phrase/rule version and default to `submitted` or `needs_user`.

### Medium: Email-body minimization budget is specified but unvalidated

The design now fixes a 10 MiB message threshold, 2 MiB decoded-text ceiling, and 20,000-character model-body allocation. The residual risk is whether these limits preserve enough evidence without leaking unnecessary text.

**Required before completing Task 4:** use evals to validate the fixed allocation and tests to prove attachments, quoted history, hidden text, tracking tokens, and oversized content are excluded.

### Low: End-user packaging remains undecided

Python, built React assets, native keyring access, and a version-matched Chromium binary need a reproducible installation/update path. This is a release reliability concern rather than a direct vulnerability.

**Required before Task 8:** select and test a packaging path on clean macOS and Linux machines, document browser download size/source, and verify uninstall/data deletion.

## Test coverage and blast radius

No implementation exists, so measured coverage and caller blast radius are unavailable. The highest planned blast-radius components are `ExecutionCoordinator`, `UrlSafetyPolicy`, `GmailGateway`, loopback mutation security, and action-state transitions. Their tests are blocking tasks rather than post-hoc coverage additions.

The implementation plan establishes public seams and requires:

- pytest for domain, API, migrations, adapters, recovery, and hostile endpoints;
- Vitest/Testing Library for component behavior;
- Playwright against the real React–FastAPI–SQLite stack, with only third-party boundaries faked;
- a dedicated credentialed Gmail/OpenAI release smoke test outside CI.

## Recommendations

### Blocking before implementation reaches the relevant task

- [ ] Validate supported `keyring` backends, failure copy, deletion, and headless behavior before completing Task 2.
- [ ] Validate the fixed body selection/minimization budget with unit tests and classification evals before completing Task 4.
- [ ] Validate the conservative semantic confirmation allowlist against negative and adversarial pages before enabling Task 7's browser executor.
- [ ] Preserve the four adversarial gates above as release-blocking tests.

### Before public V1

- [ ] Run a real code differential review of auth, sanitizer, URL policy, plan confirmation, encryption, mail reconciliation, and browser executor changes.
- [ ] Inspect SQLite, logs, screenshots, traces, browser profiles, and generated fixtures for private content.
- [ ] Perform manual VoiceOver/NVDA and browser-takeover exercises.
- [ ] Complete the real Gmail/OpenAI controlled smoke test.

## Methodology

**Strategy:** Adapted deep review for a small, greenfield planning set.  
**Techniques:** trust-boundary mapping, invariant review, adversarial scenarios, planned test-seam analysis, residual-risk and release-gate review.  
**Unavailable techniques:** baseline diff, Git blame, caller counts, historical regression search, executable proof of concept, actual test coverage.  
**Final confidence:** Medium overall; high for identifying planned attack surfaces, low for whether future code enforces the controls.
