from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.auth import create_auth_router
from app.api.health import router as health_router
from app.api.scans import create_scan_router
from app.api.security import SessionRegistry, create_local_security
from app.classification.openai_agent import OpenAIAgentsClassifier
from app.config import Settings
from app.gmail.google_gateway import GoogleOAuthProvider, StoredCredentialGmailGateway
from app.gmail.oauth import OAuthCoordinator
from app.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from app.pipeline import InMemoryCandidateCatalog, ProcessingPipeline
from app.scan.checkpoints import SqliteScanCheckpointStore
from app.scan.service import ScanService
from app.security.secrets import InsecureCredentialBackend, KeyringCredentialStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPOSITORY_ROOT / "frontend" / "dist"
RESERVED_PREFIXES = ("api", "auth", "events")


def create_app(
    settings: Settings | None = None,
    *,
    oauth_coordinator: OAuthCoordinator | None = None,
    scan_service: ScanService | None = None,
) -> FastAPI:
    settings = settings or Settings()
    candidate_catalog = InMemoryCandidateCatalog()
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
    if scan_service is None and credential_store is not None:
        engine = create_database_engine(settings.database_url)
        initialize_database(engine)
        scan_service = ScanService(
            StoredCredentialGmailGateway(credential_store),
            SqliteScanCheckpointStore(create_session_factory(engine)),
            ProcessingPipeline(OpenAIAgentsClassifier(), candidate_catalog),
        )
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
    application.include_router(create_scan_router(scan_service, local_security.require_mutation))

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
