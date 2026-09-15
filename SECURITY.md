# Security policy

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for this repository. Do not include real OAuth
tokens, signed unsubscribe URLs, cookies, complete email bodies, API keys, or database copies in an
issue. Provide a minimal synthetic reproduction and the affected commit instead.

## Supported version

Security fixes target the current `main` branch until the project publishes versioned releases.

## Threat model and controls

The app treats email content, model output, DNS/HTTP responses, and sender-owned pages as hostile.
The main risks are OAuth theft, prompt injection, SSRF/DNS rebinding, stale or accidental consent,
duplicate side effects, browser credential leakage, XSS/CSRF, and sensitive-data persistence.

Controls include:

- loopback binding plus strict Host, Origin, HttpOnly/SameSite session, and bound CSRF validation;
- restrictive CSP, no framing, no MIME sniffing, no referrer, and disabled sensitive browser APIs;
- Gmail read-only OAuth first, incremental send scope, PKCE/state, OS credential storage, and
  best-effort Google token revocation before local credential deletion;
- no full-body persistence by default and no sensitive URL/body/token logging;
- fixed classifier instructions, explicit untrusted-data delimiters, strict structured output, one
  bounded read-only tool, local evidence validation, disabled sensitive tracing, and abstention;
- plan-time and connection-time public-IP validation, connection pinning, HTTPS/default-port only,
  no credentials or fragments, no RFC redirects, bounded time/body sizes, and proxy bypass;
- AES-256-GCM action payloads bound to the action ID/schema version;
- durable action states, deterministic mail Message-ID reconciliation, and no automatic replay of
  uncertain POST/email/browser side effects;
- fresh Playwright profiles, service workers/extensions/downloads/permissions blocked, every request
  intercepted, popup/cross-origin ambiguity paused, and profiles removed after completion/expiry.

## Local security expectations

Run only on a trusted single-user machine. Keep `.env`, Google client JSON, OS login credentials, and
the local SQLite database private. Use a dedicated Gmail account for development. Do not expose port
8000 to a LAN, tunnel, container ingress, or public reverse proxy.

Disconnecting Gmail first attempts Google's revocation endpoint, then removes the local credential
even if the network revocation is unavailable. Before sharing diagnostics, inspect them for addresses
and metadata even though bodies/tokens/targets are designed not to be logged.

## Release checks

`make verify` is the non-credentialed automated gate. `make smoke-real-read` safely proves one real
Gmail body and OpenAI classification; `make smoke-real` is a separate destructive gate for controlled
accounts/endpoints. Neither runs in CI. A release also requires keyboard, VoiceOver or NVDA,
forced-colors/reduced-motion, disconnect, takeover, and local storage/log inspection checks.
