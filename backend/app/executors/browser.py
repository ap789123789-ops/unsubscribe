import asyncio
import re
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import (
    BrowserContext,
    Download,
    Page,
    Playwright,
    Request,
    Route,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from app.domain.state_machine import ActionState
from app.executors.browser_policy import BrowserOutcomePolicy
from app.executors.models import BrowserPayload, ExecutionResult
from app.security.url_policy import UnsafeTarget, UrlSafetyPolicy

UNSUBSCRIBE_CONTROL = re.compile(r"\b(unsubscribe|opt[ -]?out|remove me)\b", re.I)
LOGIN_OR_CHALLENGE = re.compile(
    r"\b(sign in|log in|password|two.factor|verification code|captcha|verify you are human|mfa)\b",
    re.I,
)


@dataclass(frozen=True)
class BrowserSessionSnapshot:
    id: str
    action_id: str
    state: ActionState
    blocker_code: str
    blocker_detail: str
    origin: str
    navigation_count: int
    blocked_request_count: int
    final_click_issued: bool
    manual_takeover: bool


@dataclass
class BrowserSession:
    id: str
    action_id: str
    playwright: Playwright
    context: BrowserContext
    page: Page
    profile_path: Path
    origin: str
    state: ActionState = ActionState.EXECUTING
    blocker_code: str = ""
    blocker_detail: str = ""
    navigation_count: int = 0
    blocked_request_count: int = 0
    final_click_issued: bool = False
    manual_takeover: bool = False

    def snapshot(self) -> BrowserSessionSnapshot:
        return BrowserSessionSnapshot(
            id=self.id,
            action_id=self.action_id,
            state=self.state,
            blocker_code=self.blocker_code,
            blocker_detail=self.blocker_detail,
            origin=self.origin,
            navigation_count=self.navigation_count,
            blocked_request_count=self.blocked_request_count,
            final_click_issued=self.final_click_issued,
            manual_takeover=self.manual_takeover,
        )


class BrowserSessionRegistry:
    def __init__(self, profile_root: Path | None = None) -> None:
        self.profile_root = (
            profile_root or Path(tempfile.gettempdir()) / "gmail-unsubscribe-browser"
        )
        self.profile_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, BrowserSession] = {}

    def create_profile(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="session-", dir=self.profile_root))

    def add(self, session: BrowserSession) -> None:
        self._sessions[session.id] = session

    def get(self, session_id: str) -> BrowserSession:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise KeyError("Browser session not found") from error

    def get_snapshot(self, session_id: str | None) -> BrowserSessionSnapshot:
        if session_id is None:
            raise KeyError("Browser session not found")
        return self.get(session_id).snapshot()

    def snapshots(self) -> tuple[BrowserSessionSnapshot, ...]:
        return tuple(session.snapshot() for session in self._sessions.values())

    def remove(self, session_id: str) -> BrowserSession | None:
        return self._sessions.pop(session_id, None)


class BrowserExecutor:
    def __init__(
        self,
        *,
        policy: UrlSafetyPolicy,
        registry: BrowserSessionRegistry,
        headless: bool = False,
        navigation_timeout_ms: int = 10_000,
    ) -> None:
        self._policy = policy
        self._registry = registry
        self._headless = headless
        self._navigation_timeout_ms = navigation_timeout_ms
        self._outcomes = BrowserOutcomePolicy()

    async def execute(self, action_id: str, payload: BrowserPayload) -> ExecutionResult:
        try:
            target = await self._policy.revalidate_before_connect(payload.target)
        except UnsafeTarget:
            return ExecutionResult(
                state=ActionState.FAILED,
                evidence_code="browser_target_revalidation_failed",
                safe_detail="The website failed its final public-network safety check.",
            )
        try:
            session = await self._launch(action_id, target.origin)
        except Exception:
            return ExecutionResult(
                state=ActionState.FAILED,
                evidence_code="browser_launch_failed",
                safe_detail="The isolated browser could not be opened.",
            )
        self._registry.add(session)
        await self._install_guards(session)
        try:
            await session.page.goto(
                target.url,
                wait_until="domcontentloaded",
                timeout=self._navigation_timeout_ms,
            )
        except Exception:
            if not session.blocker_code:
                session.blocker_code = "navigation_failed"
                session.blocker_detail = "The unsubscribe page did not finish opening."
        return await self._advance(session)

    async def take_over(self, session_id: str) -> BrowserSessionSnapshot:
        session = self._registry.get(session_id)
        session.manual_takeover = True
        session.state = ActionState.NEEDS_USER
        if not session.page.is_closed():
            await session.page.bring_to_front()
        return session.snapshot()

    async def resume(self, session_id: str) -> ExecutionResult:
        session = self._registry.get(session_id)
        if session.page.is_closed():
            return await self._needs_user(
                session,
                "browser_window_closed",
                "The separate browser window closed before the outcome was known.",
            )
        session.blocker_code = ""
        session.blocker_detail = ""
        session.state = ActionState.EXECUTING
        if session.manual_takeover or session.final_click_issued:
            text = await self._visible_text(session.page)
            outcome = self._outcomes.evaluate(
                text,
                final_click_issued=session.final_click_issued,
            )
            if outcome.state is ActionState.NEEDS_USER:
                return await self._needs_user(
                    session,
                    outcome.evidence_code,
                    "The page still does not show an explicit result; no click was repeated.",
                )
            return await self._finish(
                session,
                ExecutionResult(
                    state=outcome.state,
                    evidence_code=outcome.evidence_code,
                    safe_detail=outcome.safe_detail,
                ),
            )
        return await self._advance(session)

    async def cancel(self, session_id: str) -> BrowserSessionSnapshot:
        session = self._registry.get(session_id)
        snapshot = session.snapshot()
        await self._close(session)
        return snapshot

    async def _launch(self, action_id: str, origin: str) -> BrowserSession:
        profile = self._registry.create_profile()
        playwright = await async_playwright().start()
        try:
            context = await playwright.chromium.launch_persistent_context(
                str(profile),
                headless=self._headless,
                accept_downloads=False,
                service_workers="block",
                args=[
                    "--disable-extensions",
                    "--disable-component-extensions-with-background-pages",
                ],
            )
            await context.clear_permissions()
            page = context.pages[0] if context.pages else await context.new_page()
        except Exception:
            await playwright.stop()
            self._remove_profile(profile)
            raise
        return BrowserSession(
            id=str(uuid4()),
            action_id=action_id,
            playwright=playwright,
            context=context,
            page=page,
            profile_path=profile,
            origin=origin,
        )

    async def _install_guards(self, session: BrowserSession) -> None:
        async def route_request(route: Route, request: Request) -> None:
            allowed = await self._policy.allow_browser_request(request.url)
            if not allowed:
                session.blocked_request_count += 1
                if request.is_navigation_request() and request.frame == session.page.main_frame:
                    self._block(
                        session,
                        "unsafe_navigation",
                        "The page tried to navigate to a non-public or unsafe destination.",
                    )
                await route.abort("blockedbyclient")
                return
            if request.is_navigation_request() and request.frame == session.page.main_frame:
                request_origin = self._origin(request.url)
                if request_origin != session.origin:
                    session.blocked_request_count += 1
                    self._block(
                        session,
                        "cross_origin_navigation",
                        "The page tried to move to a different website.",
                    )
                    await route.abort("blockedbyclient")
                    return
                if not session.final_click_issued:
                    session.navigation_count += 1
                    if session.navigation_count > 2:
                        session.blocked_request_count += 1
                        session.blocker_code = "navigation_limit_reached"
                        session.blocker_detail = (
                            "The page exceeded the two-navigation safety limit."
                        )
                        await route.abort("blockedbyclient")
                        return
            await route.continue_()

        await session.context.route("**/*", route_request)

        async def close_popup(popup: Page) -> None:
            self._block(
                session,
                "popup_blocked",
                "The page tried to open another window.",
            )
            await popup.close()

        async def cancel_download(download: Download) -> None:
            self._block(
                session,
                "download_blocked",
                "The page tried to download a file.",
            )
            await download.cancel()

        session.page.on("popup", lambda popup: asyncio.create_task(close_popup(popup)))
        session.page.on("download", lambda download: asyncio.create_task(cancel_download(download)))
        session.page.on(
            "requestfailed",
            lambda request: self._record_failed_navigation(session, request),
        )
        session.page.on(
            "dialog",
            lambda dialog: asyncio.create_task(self._dismiss_dialog(session, dialog)),
        )

    async def _dismiss_dialog(self, session: BrowserSession, dialog) -> None:
        self._block(
            session,
            "dialog_blocked",
            "The page opened a confirmation dialog that needs your review.",
        )
        await dialog.dismiss()

    def _record_failed_navigation(
        self, session: BrowserSession, request: Request
    ) -> None:
        if (
            session.final_click_issued
            and request.is_navigation_request()
            and request.frame == session.page.main_frame
        ):
            self._block(
                session,
                "final_navigation_failed",
                "The destination disconnected after the final click; the outcome is uncertain.",
            )

    async def _advance(self, session: BrowserSession) -> ExecutionResult:
        if session.blocker_code:
            return await self._needs_user(
                session, session.blocker_code, session.blocker_detail
            )
        if session.page.is_closed():
            return await self._needs_user(
                session,
                "browser_window_closed",
                "The separate browser window closed before the outcome was known.",
            )
        text = await self._visible_text(session.page)
        initial = self._outcomes.evaluate(text, final_click_issued=False)
        if initial.state is ActionState.CONFIRMED:
            return await self._finish(
                session,
                ExecutionResult(initial.state, initial.evidence_code, initial.safe_detail),
            )
        password_fields = await session.page.locator('input[type="password"]').count()
        if password_fields or LOGIN_OR_CHALLENGE.search(text):
            return await self._needs_user(
                session,
                "login_required",
                "Sign-in, MFA, or a human-verification challenge needs your help.",
            )
        controls = await self._unsubscribe_controls(session.page)
        if not controls:
            return await self._needs_user(
                session,
                "unsubscribe_control_not_found",
                "No unambiguous unsubscribe control was found.",
            )
        if len(controls) > 1:
            return await self._needs_user(
                session,
                "ambiguous_unsubscribe_choice",
                "The page offers multiple unsubscribe choices.",
            )
        control = controls[0]
        preflight = await self._control_blocker(session, control)
        if preflight is not None:
            return await self._needs_user(session, *preflight)

        previous_text = text
        session.final_click_issued = True
        try:
            await control.click(timeout=self._navigation_timeout_ms)
            await asyncio.sleep(0)
            with suppress(PlaywrightTimeoutError):
                await session.page.wait_for_function(
                    "previous => document.body && document.body.innerText !== previous",
                    arg=previous_text,
                    timeout=min(self._navigation_timeout_ms, 2_000),
                )
        except Exception:
            return await self._needs_user(
                session,
                "final_click_uncertain",
                "The final click outcome is uncertain; it will not be repeated automatically.",
            )
        if session.blocker_code:
            return await self._needs_user(
                session, session.blocker_code, session.blocker_detail
            )
        if session.page.is_closed():
            return await self._needs_user(
                session,
                "browser_window_closed",
                "The window closed after the final click; the outcome is uncertain.",
            )
        outcome = self._outcomes.evaluate(
            await self._visible_text(session.page), final_click_issued=True
        )
        return await self._finish(
            session,
            ExecutionResult(outcome.state, outcome.evidence_code, outcome.safe_detail),
        )

    async def _unsubscribe_controls(self, page: Page):
        controls = []
        for role in ("button", "link"):
            locator = page.get_by_role(role, name=UNSUBSCRIBE_CONTROL)
            for index in range(await locator.count()):
                candidate = locator.nth(index)
                if await candidate.is_visible() and await candidate.is_enabled():
                    controls.append(candidate)
        return controls

    async def _control_blocker(self, session: BrowserSession, control) -> tuple[str, str] | None:
        target = (await control.get_attribute("target") or "").lower()
        onclick = (await control.get_attribute("onclick") or "").lower()
        download = await control.get_attribute("download")
        href = await control.get_attribute("href")
        form_action = await control.evaluate(
            "element => element.closest('form') ? element.closest('form').action : ''"
        )
        destination = href or form_action
        if target == "_blank" or "window.open" in onclick:
            return "popup_requires_review", "This control opens another window."
        if download is not None:
            return "download_requires_review", "This control downloads a file."
        if destination:
            absolute = urlsplit(session.page.url).geturl()
            resolved = await control.evaluate(
                "(element, fallback) => element.href || "
                "(element.closest('form') ? element.closest('form').action : fallback)",
                absolute,
            )
            if self._origin(str(resolved)) != session.origin:
                return (
                    "cross_origin_navigation",
                    "The final control points to a different website.",
                )
        return None

    async def _needs_user(
        self, session: BrowserSession, code: str, detail: str
    ) -> ExecutionResult:
        session.state = ActionState.NEEDS_USER
        session.blocker_code = code
        session.blocker_detail = detail
        return ExecutionResult(
            state=ActionState.NEEDS_USER,
            evidence_code=code,
            safe_detail=detail,
            external_id=session.id,
        )

    async def _finish(
        self, session: BrowserSession, result: ExecutionResult
    ) -> ExecutionResult:
        session.state = result.state
        await self._close(session)
        return result

    async def _close(self, session: BrowserSession) -> None:
        self._registry.remove(session.id)
        try:
            await session.context.close()
        finally:
            await session.playwright.stop()
            self._remove_profile(session.profile_path)

    def _remove_profile(self, profile: Path) -> None:
        root = self._registry.profile_root.resolve()
        resolved = profile.resolve()
        if resolved.parent != root or not resolved.name.startswith("session-"):
            raise RuntimeError("Refusing to remove an unexpected browser profile path")
        shutil.rmtree(resolved, ignore_errors=True)

    @staticmethod
    async def _visible_text(page: Page) -> str:
        try:
            return await page.locator("body").inner_text(timeout=2_000)
        except Exception:
            return ""

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme == "file":
            return "file://"
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @staticmethod
    def _block(session: BrowserSession, code: str, detail: str) -> None:
        if not session.blocker_code:
            session.blocker_code = code
            session.blocker_detail = detail
