from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.actions.browser_sessions import BrowserSessionService
from app.actions.coordinator import ExecutionCoordinator
from app.actions.planner import ActionPlanService
from app.api.action_plans import create_action_plan_router
from app.api.auth import create_auth_router
from app.api.browser_sessions import create_browser_session_router
from app.api.candidates import create_candidate_router
from app.api.events import create_event_router
from app.api.health import Readiness, create_health_router
from app.api.scans import create_scan_router
from app.api.security import SessionRegistry, create_local_security
from app.classification.openai_agent import OpenAIAgentsClassifier
from app.config import Settings
from app.executors.browser import BrowserExecutor, BrowserSessionRegistry
from app.executors.mailto import MailtoExecutor
from app.executors.rfc8058 import HttpxRfcTransport, Rfc8058Executor
from app.gmail.google_gateway import GoogleOAuthProvider, StoredCredentialGmailGateway
from app.gmail.oauth import OAuthCoordinator
from app.observability import configure_app_logging
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    run_migrations,
)
from app.persistence.repositories import ActionRepository
from app.pipeline import InMemoryCandidateCatalog, ProcessingPipeline
from app.recovery import RecoveryService, StartupRecovery
from app.scan.checkpoints import SqliteScanCheckpointStore
from app.scan.service import ScanService
from app.security.payload_crypto import PayloadCipher, PayloadKeyUnavailable
from app.security.secrets import InsecureCredentialBackend, KeyringCredentialStore
from app.security.url_policy import UrlSafetyPolicy

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPOSITORY_ROOT / "frontend" / "dist"
RESERVED_PREFIXES = ("api", "auth", "events")
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
    )
)


def create_app(
    settings: Settings | None = None,
    *,
    oauth_coordinator: OAuthCoordinator | None = None,
    scan_service: ScanService | None = None,
    candidate_catalog: InMemoryCandidateCatalog | None = None,
    action_plan_service: ActionPlanService | None = None,
    execution_coordinator: ExecutionCoordinator | None = None,
    browser_session_service: BrowserSessionService | None = None,
    event_repository: ActionRepository | None = None,
    startup_migrator: Callable[[], None] | None = None,
    recovery_service: StartupRecovery | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_app_logging(settings)
    catalog_was_injected = candidate_catalog is not None
    candidate_catalog = candidate_catalog or InMemoryCandidateCatalog()
    url_policy = UrlSafetyPolicy()
    action_plan_service = action_plan_service or ActionPlanService(
        candidate_catalog,
        url_policy=None if catalog_was_injected else url_policy,
    )
    credential_store: KeyringCredentialStore | None = None
    if (
        settings.enable_external_services
        and oauth_coordinator is None
        and settings.google_client_secrets_file is not None
    ):
        try:
            credential_store = KeyringCredentialStore()
            oauth_coordinator = OAuthCoordinator(
                GoogleOAuthProvider(
                    client_secrets_file=settings.google_client_secrets_file,
                    redirect_uri=settings.oauth_redirect_uri,
                ),
                credential_store,
            )
        except InsecureCredentialBackend:
            oauth_coordinator = None
            credential_store = None
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    startup_migrator = startup_migrator or partial(run_migrations, settings.database_url)
    action_repository = ActionRepository(session_factory)
    event_repository = event_repository or action_repository
    scan_checkpoints: SqliteScanCheckpointStore | None = None
    browser_registry = BrowserSessionRegistry(settings.browser_profile_root)
    browser_executor: BrowserExecutor | None = None
    gmail_gateway = (
        StoredCredentialGmailGateway(credential_store) if credential_store is not None else None
    )
    if scan_service is None and gmail_gateway is not None:
        scan_checkpoints = SqliteScanCheckpointStore(session_factory)
        scan_service = ScanService(
            gmail_gateway,
            scan_checkpoints,
            ProcessingPipeline(
                OpenAIAgentsClassifier(
                    api_key=(
                        settings.openai_api_key.get_secret_value()
                        if settings.openai_api_key is not None
                        else None
                    )
                ),
                candidate_catalog,
            ),
        )
    if execution_coordinator is None and credential_store is not None and gmail_gateway is not None:
        try:
            browser_executor = BrowserExecutor(
                policy=url_policy,
                registry=browser_registry,
                headless=settings.browser_headless,
                navigation_timeout_ms=settings.browser_navigation_timeout_ms,
            )
            execution_coordinator = ExecutionCoordinator(
                plans=action_plan_service,
                repository=action_repository,
                cipher=PayloadCipher.from_credential_store(credential_store),
                rfc8058=Rfc8058Executor(
                    policy=url_policy,
                    transport=HttpxRfcTransport(),
                ),
                mailto=MailtoExecutor(gmail=gmail_gateway, journal=action_repository),
                browser=browser_executor,
            )
            browser_session_service = BrowserSessionService(
                executor=browser_executor,
                registry=browser_registry,
                repository=action_repository,
            )
        except PayloadKeyUnavailable:
            execution_coordinator = None
    if recovery_service is None:
        recovery_service = RecoveryService(
            repository=action_repository,
            gmail=gmail_gateway,
            scan_service=scan_service,
            scan_checkpoints=scan_checkpoints,
            browser_registry=browser_registry,
            browser_profile_ttl=timedelta(seconds=settings.browser_profile_ttl_seconds),
        )
    readiness = Readiness()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        readiness.ready = False
        application.state.ready = False
        if startup_migrator is not None:
            startup_migrator()
        if recovery_service is not None:
            application.state.recovery_report = await recovery_service.run()
        readiness.ready = True
        application.state.ready = True
        try:
            yield
        finally:
            readiness.ready = False
            application.state.ready = False
            if browser_executor is not None:
                await browser_executor.close_all()

    application = FastAPI(
        title="Gmail Unsubscribe Agent API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.ready = False
    application.state.candidate_catalog = candidate_catalog

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["X-Frame-Options"] = "DENY"
        return response

    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )
    application.include_router(create_health_router(readiness))
    application.include_router(create_event_router(event_repository))
    local_security = create_local_security(
        SessionRegistry(),
        frozenset(settings.allowed_origins),
    )
    application.include_router(local_security.router)
    application.include_router(
        create_auth_router(oauth_coordinator, local_security.require_mutation)
    )
    application.include_router(
        create_browser_session_router(
            browser_session_service,
            local_security.require_mutation,
        )
    )
    application.include_router(create_scan_router(scan_service, local_security.require_mutation))
    application.include_router(
        create_candidate_router(candidate_catalog, local_security.require_mutation)
    )
    application.include_router(
        create_action_plan_router(
            action_plan_service,
            local_security.require_mutation,
            execution_coordinator,
        )
    )

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def frontend(full_path: str) -> FileResponse:
        first_segment = full_path.split("/", 1)[0]
        index = FRONTEND_DIST / "index.html"
        if first_segment in RESERVED_PREFIXES or not index.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index)

    return application


app = create_app()
