from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.health import router as health_router

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPOSITORY_ROOT / "frontend" / "dist"
RESERVED_PREFIXES = ("api", "auth", "events")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Gmail Unsubscribe Agent API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/openapi.json",
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    application.include_router(health_router)

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

