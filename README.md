# Gmail Unsubscribe Agent

A local React + Python application for finding Gmail subscriptions, classifying them with OpenAI
`gpt-5-mini`, reviewing them by category, and safely attempting unsubscribe actions only after the
user confirms an exact plan.

V1 is implemented but is not a credential-free demo. Automated tests use synthetic third-party
boundaries; actual product acceptance requires your real Gmail OAuth credential, a complete message
body, the OpenAI API, and controlled real unsubscribe endpoints.

## Safety model

- The classifier only classifies and explains. It cannot unsubscribe, browse, send, or approve.
- Nothing is selected by default. Candidate revisions and the plan digest prevent stale consent.
- RFC 8058 and `mailto:` report **submitted**, not confirmed. Only explicit allowlisted browser-page
  language can report **confirmed**.
- A possibly issued POST, email, or final browser click is never automatically repeated.
- Equivalent freshly-created plans cannot repeat an unchanged action that was already attempted.
- Signed targets are AES-256-GCM encrypted at rest; credentials use macOS Keychain or Linux Secret
  Service; complete bodies stay in memory by default.
- RFC and browser connections pin the public IP validated immediately before connection. Browser
  fallback also uses a fresh profile, same-origin request guards, two pre-submit navigations, one
  final click, and user takeover without dropping the guards.

## Prerequisites

- Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and npm
- A Google Cloud OAuth **Desktop app** client with Gmail API enabled
- An OpenAI API key
- macOS Keychain or Linux Secret Service

Configure the exact Google callback as:

```text
http://127.0.0.1:8000/auth/google/callback
```

## Install and run

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` and `APP_GOOGLE_CLIENT_SECRETS_FILE` in `.env`; never commit `.env` or the
Google client JSON. Then:

```bash
make setup
cd backend && uv run playwright install chromium && cd ..
npm --prefix frontend exec playwright install chromium
make build
make dev-backend
```

Open `http://127.0.0.1:8000`. Connect Gmail, run a bounded scan, review the collapsible categories,
inspect/correct classifications, select subscriptions, and confirm the exact action plan.

For split frontend development, run `make dev-backend` and `make dev-frontend` in separate terminals.

## Verification

```bash
make lint
make typecheck
make test
make verify
```

`make verify` runs locked dependency validation, Python formatting/lint/type checks, unit/API/
integration/eval tests, frontend lint/type/component/build checks, OpenAPI client drift detection,
and the full React–FastAPI Playwright suite with axe security/accessibility assertions.

CI never receives Gmail or OpenAI secrets. It fakes only external providers and sender sites.

## Safe credentialed read/classification smoke

First connect Gmail through the app. Set the expected address in the terminal (it is deliberately
not stored in the repository), optionally narrow the Gmail query to a safe label, and run:

```bash
export UNSUBSCRIBE_SMOKE_EXPECTED_GMAIL='your-test-account@example.com'
# Optional: export UNSUBSCRIBE_SMOKE_GMAIL_QUERY='label:unsubscribe-smoke'
make smoke-real-read
```

This makes one real Gmail profile call, retrieves one complete message, and sends its sanitized,
bounded classification payload to OpenAI `gpt-5-mini`. It does not send mail, visit an unsubscribe
URL, or unsubscribe. The OpenAI SDK receives the key from `.env` through the typed backend settings;
the key is not printed or stored in SQLite. Official OpenAI guidance recommends keeping API keys in
environment variables or server-side secret management.

## Destructive executor release smoke

Use a dedicated Gmail account and endpoints you own. This command sends real requests and a real
email; the acknowledgement is deliberately hard to set accidentally.

```bash
export UNSUBSCRIBE_REAL_SMOKE_ACK=I_UNDERSTAND_THIS_SENDS_REAL_UNSUBSCRIBE_REQUESTS
export UNSUBSCRIBE_SMOKE_EXPECTED_GMAIL='your-test-account@example.com'
export UNSUBSCRIBE_SMOKE_RFC_URL='https://your-controlled-fixture.example/one-click'
export UNSUBSCRIBE_SMOKE_MAILTO='mailto:your-controlled-inbox@example.com?subject=Unsubscribe'
export UNSUBSCRIBE_SMOKE_BROWSER_URL='https://your-controlled-fixture.example/browser'
# Optional: export UNSUBSCRIBE_SMOKE_GMAIL_QUERY='label:your-safe-smoke-label'
make smoke-real
```

This separate gate verifies the Gmail profile, retrieves one full message, classifies its body with
`gpt-5-mini`, then exercises controlled RFC, mailto, and visible-browser paths once. Do not run it
until all three targets are dedicated fixtures you own.

## Known V1 limits

- One Gmail account and English browser confirmation phrases.
- Local loopback process; no packaged installer yet.
- Metadata/history retention and a one-click delete-local-data feature remain product decisions.
- Sender websites are adversarial and inconsistent; ambiguous paths pause for the user.

See [technical design](docs/06-detailed-technical-design.md), [security](SECURITY.md), and
[contributing](CONTRIBUTING.md).

Licensed under the [MIT License](LICENSE).
