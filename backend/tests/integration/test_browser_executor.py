from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import pytest

from app.domain.state_machine import ActionState
from app.executors.browser import (
    BrowserExecutor,
    BrowserSessionRegistry,
    chromium_pinning_args,
)
from app.executors.browser_policy import BrowserOutcomePolicy
from app.executors.models import BrowserPayload
from app.security.url_policy import ValidatedTarget


class FixtureNetworkPolicy:
    def __init__(self) -> None:
        self.checked: list[str] = []
        self.blocked: list[str] = []

    async def revalidate_before_connect(self, target):
        return target

    async def allow_browser_request(self, target: str) -> bool:
        self.checked.append(target)
        allowed = not target.startswith(("http://127.", "http://169.254."))
        if not allowed:
            self.blocked.append(target)
        return allowed


def fixture_target(path: Path) -> ValidatedTarget:
    return ValidatedTarget(
        url=path.as_uri(),
        origin="file://",
        hostname="fixture.local",
        addresses=("93.184.216.34",),
    )


def web_target(url: str) -> ValidatedTarget:
    parsed = urlsplit(url)
    return ValidatedTarget(
        url=url,
        origin=f"{parsed.scheme}://{parsed.netloc}",
        hostname=parsed.hostname or "fixture.local",
        addresses=(parsed.hostname or "127.0.0.1",),
    )


def test_browser_pins_chromium_to_the_final_validated_address() -> None:
    target = ValidatedTarget(
        url="https://mail.example/unsubscribe",
        origin="https://mail.example",
        hostname="mail.example",
        addresses=("93.184.216.34", "93.184.216.35"),
    )

    assert chromium_pinning_args(target)[-1] == (
        "--host-resolver-rules=MAP mail.example 93.184.216.34, EXCLUDE localhost"
    )


def write_fixture(path: Path, body: str) -> Path:
    path.write_text(f"<!doctype html><html><body><main>{body}</main></body></html>")
    return path


@pytest.mark.parametrize(
    ("text", "clicked", "expected"),
    [
        ("You have been unsubscribed", True, ActionState.CONFIRMED),
        ("Email preferences updated", True, ActionState.CONFIRMED),
        ("Could not unsubscribe you", True, ActionState.FAILED),
        ("Se ha enviado su solicitud", True, ActionState.SUBMITTED),
        ("Welcome", False, ActionState.NEEDS_USER),
    ],
)
def test_browser_semantic_outcomes_are_versioned_and_honest(
    text: str, clicked: bool, expected: ActionState
) -> None:
    result = BrowserOutcomePolicy().evaluate(text, final_click_issued=clicked)
    assert result.state is expected
    assert result.rule_version == "browser-outcome-en-v1"


async def test_browser_confirms_positive_evidence_and_blocks_private_subresource(
    tmp_path: Path,
) -> None:
    fixture = write_fixture(
        tmp_path / "success.html",
        """
        <img src="http://127.0.0.1:9/private.png">
        <iframe src="http://169.254.169.254/private-frame"></iframe>
        <script>fetch('http://127.0.0.1:9/private-fetch').catch(() => {})</script>
        <button onclick="document.querySelector('main').textContent='You have been unsubscribed'">
          Unsubscribe
        </button>
        """,
    )
    policy = FixtureNetworkPolicy()
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=policy,
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-success", BrowserPayload(fixture_target(fixture)))

    assert result.state is ActionState.CONFIRMED
    assert result.evidence_code == "browser_semantic_acceptance_v1"
    assert {urlsplit(url).path for url in policy.blocked} == {
        "/private.png",
        "/private-frame",
        "/private-fetch",
    }
    assert registry.snapshots() == ()
    assert list((tmp_path / "profiles").iterdir()) == []


@pytest.mark.parametrize(
    "challenge",
    [
        '<label>Password <input type="password"></label>',
        "Complete the CAPTCHA to continue",
        "Enter your MFA verification code",
    ],
)
async def test_browser_pauses_for_login_or_human_challenge_without_clicking(
    tmp_path: Path, challenge: str
) -> None:
    fixture = write_fixture(
        tmp_path / "login.html",
        f"{challenge}<button>Unsubscribe</button>",
    )
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-login", BrowserPayload(fixture_target(fixture)))

    assert result.state is ActionState.NEEDS_USER
    assert result.evidence_code == "login_required"
    assert result.external_id is not None
    snapshot = registry.get_snapshot(result.external_id)
    assert snapshot.final_click_issued is False
    await executor.cancel(result.external_id)
    assert registry.snapshots() == ()


async def test_browser_reports_a_window_closed_during_user_intervention(
    tmp_path: Path,
) -> None:
    fixture = write_fixture(
        tmp_path / "close.html",
        '<label>Password <input type="password"></label><button>Unsubscribe</button>',
    )
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )
    paused = await executor.execute("action-close", BrowserPayload(fixture_target(fixture)))
    await registry.get(paused.external_id).page.close()

    resumed = await executor.resume(paused.external_id)

    assert resumed.state is ActionState.NEEDS_USER
    assert resumed.evidence_code == "browser_window_closed"
    assert registry.get_snapshot(paused.external_id).final_click_issued is False
    await executor.cancel(paused.external_id)


async def test_browser_pauses_for_ambiguous_controls(tmp_path: Path) -> None:
    ambiguous = write_fixture(
        tmp_path / "ambiguous.html",
        "<button>Unsubscribe weekly</button><button>Unsubscribe all</button>",
    )
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-ambiguous", BrowserPayload(fixture_target(ambiguous)))

    assert result.state is ActionState.NEEDS_USER
    assert result.evidence_code == "ambiguous_unsubscribe_choice"
    assert registry.get_snapshot(result.external_id).final_click_issued is False
    await executor.cancel(result.external_id)


@pytest.mark.parametrize(
    ("markup", "expected_code"),
    [
        (
            "<button onclick=\"window.open('https://example.com/unsubscribe')\">"
            "Unsubscribe</button>",
            "popup_requires_review",
        ),
        (
            '<a href="https://different.example/unsubscribe">Unsubscribe</a>',
            "cross_origin_navigation",
        ),
        (
            '<a href="receipt.txt" download>Unsubscribe</a>',
            "download_requires_review",
        ),
    ],
)
async def test_browser_pauses_before_popup_cross_origin_or_download_control(
    tmp_path: Path, markup: str, expected_code: str
) -> None:
    fixture = write_fixture(tmp_path / f"{expected_code}.html", markup)
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute(
        f"action-{expected_code}", BrowserPayload(fixture_target(fixture))
    )

    assert result.state is ActionState.NEEDS_USER
    assert result.evidence_code == expected_code
    assert registry.get_snapshot(result.external_id).final_click_issued is False
    await executor.cancel(result.external_id)


async def test_browser_never_repeats_final_click_when_outcome_is_unmatched(
    tmp_path: Path,
) -> None:
    fixture = write_fixture(
        tmp_path / "submitted.html",
        """
        <output id="count">0</output>
        <button onclick="count.textContent=String(Number(count.textContent)+1)">Unsubscribe</button>
        """,
    )
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-once", BrowserPayload(fixture_target(fixture)))

    assert result.state is ActionState.SUBMITTED
    assert result.evidence_code == "browser_click_submitted"
    assert registry.snapshots() == ()


async def test_browser_retains_uncertain_session_after_final_click_disconnect(
    tmp_path: Path,
) -> None:
    fixture = write_fixture(
        tmp_path / "disconnect.html",
        '<a href="missing-after-click.html">Unsubscribe</a>',
    )
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-disconnect", BrowserPayload(fixture_target(fixture)))

    assert result.state is ActionState.NEEDS_USER
    assert result.evidence_code == "final_navigation_failed"
    assert registry.get_snapshot(result.external_id).final_click_issued is True
    await executor.cancel(result.external_id)


async def test_browser_blocks_the_third_pre_submission_navigation(tmp_path: Path) -> None:
    first = write_fixture(
        tmp_path / "first.html",
        '<label>Password <input type="password"></label><button>Unsubscribe</button>',
    )
    second = write_fixture(tmp_path / "second.html", "Second page")
    third = write_fixture(tmp_path / "third.html", "Third page")
    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=FixtureNetworkPolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )
    paused = await executor.execute("action-limit", BrowserPayload(fixture_target(first)))
    session = registry.get(paused.external_id)

    await session.page.goto(second.as_uri())
    with suppress(Exception):
        await session.page.goto(third.as_uri())

    snapshot = registry.get_snapshot(paused.external_id)
    assert snapshot.blocker_code == "navigation_limit_reached"
    assert snapshot.navigation_count == 3
    assert session.page.url != third.as_uri()
    await executor.cancel(paused.external_id)


@pytest.fixture
def service_worker_fixture() -> tuple[str, list[str]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/sw.js":
                body = b"self.addEventListener('fetch', () => {});"
                content_type = "text/javascript"
            elif self.path == "/pin":
                body = (
                    b'<button onclick="document.body.textContent='
                    b"'You have been unsubscribed'\">Unsubscribe</button>"
                )
                content_type = "text/html"
            else:
                body = b"""<!doctype html><html><body><main>
                    <output id="worker-state">pending</output>
                    <script>
                    navigator.serviceWorker.register('/sw.js').then(
                      () => document.querySelector('#worker-state').textContent = 'registered',
                      () => document.querySelector('#worker-state').textContent = 'blocked'
                    );
                    </script>
                    </main></body></html>"""
                content_type = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def test_browser_connects_to_the_pinned_ip_without_system_dns(
    tmp_path: Path, service_worker_fixture: tuple[str, list[str]]
) -> None:
    fixture_url, requests = service_worker_fixture
    port = urlsplit(fixture_url).port

    class PublicFixturePolicy(FixtureNetworkPolicy):
        async def allow_browser_request(self, target: str) -> bool:
            self.checked.append(target)
            return True

    target = ValidatedTarget(
        url=f"http://pinning.invalid:{port}/pin",
        origin=f"http://pinning.invalid:{port}",
        hostname="pinning.invalid",
        addresses=("127.0.0.1",),
    )
    executor = BrowserExecutor(
        policy=PublicFixturePolicy(),
        registry=BrowserSessionRegistry(profile_root=tmp_path / "profiles"),
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-pinned", BrowserPayload(target))

    assert result.state is ActionState.CONFIRMED
    assert requests == ["/pin"]


async def test_browser_blocks_service_worker_registration(
    tmp_path: Path, service_worker_fixture: tuple[str, list[str]]
) -> None:
    url, requests = service_worker_fixture

    class PublicFixturePolicy(FixtureNetworkPolicy):
        async def allow_browser_request(self, target: str) -> bool:
            self.checked.append(target)
            return True

    registry = BrowserSessionRegistry(profile_root=tmp_path / "profiles")
    executor = BrowserExecutor(
        policy=PublicFixturePolicy(),
        registry=registry,
        headless=True,
        navigation_timeout_ms=5_000,
    )

    result = await executor.execute("action-worker", BrowserPayload(web_target(url)))
    session = registry.get(result.external_id)
    registrations = await session.page.evaluate(
        "navigator.serviceWorker.getRegistrations().then(items => items.length)"
    )

    assert registrations == 0
    assert session.context.service_workers == []
    assert "/sw.js" not in requests
    await executor.cancel(result.external_id)
