from pathlib import Path

from fastapi import FastAPI, HTTPException
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
from app.api.health import router as health_router
from app.api.scans import create_scan_router
from app.api.security import SessionRegistry, create_local_security
from app.classification.openai_agent import OpenAIAgentsClassifier
from app.config import Settings
from app.executors.browser import BrowserExecutor, BrowserSessionRegistry
from app.executors.mailto import MailtoExecutor
from app.executors.rfc8058 import HttpxRfcTransport, Rfc8058Executor
from app.gmail.google_gateway import GoogleOAuthProvider, StoredCredentialGmailGateway
from app.gmail.oauth import OAuthCoordinator
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.persistence.repositories import ActionRepository
from app.pipeline import InMemoryCandidateCatalog, ProcessingPipeline
from app.scan.checkpoints import SqliteScanCheckpointStore
from app.scan.service import ScanService
from app.security.payload_crypto import PayloadCipher, PayloadKeyUnavailable
from app.security.secrets import InsecureCredentialBackend, KeyringCredentialStore
from app.security.url_policy import UrlSafetyPolicy

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPOSITORY_ROOT / "frontend" / "dist"
RESERVED_PREFIXES = ("api", "auth", "events")


def create_app(
    settings: Settings | None = None,
    *,
    oauth_coordinator: OAuthCoordinator | None = None,
    scan_service: ScanService | None = None,
    candidate_catalog: InMemoryCandidateCatalog | None = None,
    action_plan_service: ActionPlanService | None = None,
    execution_coordinator: ExecutionCoordinator | None = None,
    browser_session_service: BrowserSessionService | None = None,
) -> FastAPI:
    settings = settings or Settings()
    catalog_was_injected = candidate_catalog is not None
    candidate_catalog = candidate_catalog or InMemoryCandidateCatalog()
    url_policy = UrlSafetyPolicy()
    action_plan_service = action_plan_service or ActionPlanService(
        candidate_catalog,
        url_policy=None if catalog_was_injected else url_policy,
    )
    credential_store: KeyringCredentialStore | None = None
    if oauth_coordinator is None and settings.google_client_secrets_file is not None:
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
    session_factory = None
    if credential_store is not None:
        engine = create_database_engine(settings.database_url)
        initialize_database(engine)
        session_factory = create_session_factory(engine)
    gmail_gateway = (
        StoredCredentialGmailGateway(credential_store)
        if credential_store is not None
        else None
    )
    if scan_service is None and gmail_gateway is not None and session_factory is not None:
        scan_service = ScanService(
            gmail_gateway,
            SqliteScanCheckpointStore(session_factory),
            ProcessingPipeline(OpenAIAgentsClassifier(), candidate_catalog),
        )
    if (
        execution_coordinator is None
        and credential_store is not None
        and gmail_gateway is not None
        and session_factory is not None
    ):
        try:
            repository = ActionRepository(session_factory)
            browser_registry = BrowserSessionRegistry(settings.browser_profile_root)
            browser_executor = BrowserExecutor(
                policy=url_policy,
                registry=browser_registry,
                headless=settings.browser_headless,
                navigation_timeout_ms=settings.browser_navigation_timeout_ms,
            )
            execution_coordinator = ExecutionCoordinator(
                plans=action_plan_service,
                repository=repository,
                cipher=PayloadCipher.from_credential_store(credential_store),
                rfc8058=Rfc8058Executor(
                    policy=url_policy,
                    transport=HttpxRfcTransport(),
                ),
                mailto=MailtoExecutor(gmail=gmail_gateway, journal=repository),
                browser=browser_executor,
            )
            browser_session_service = BrowserSessionService(
                executor=browser_executor,
                registry=browser_registry,
                repository=repository,
            )
        except PayloadKeyUnavailable:
            execution_coordinator = None
    application = FastAPI(
        title="Gmail Unsubscribe Agent API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/openapi.json",
    )
    application.state.candidate_catalog = candidate_catalog
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )
    application.include_router(health_router)
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
