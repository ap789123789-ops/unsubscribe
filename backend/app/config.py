from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    database_url: str = "sqlite:///./unsubscribe.db"
    frontend_dist: Path | None = None
    google_client_secrets_file: Path | None = None
    oauth_redirect_uri: str = "http://127.0.0.1:8000/auth/google/callback"
    browser_headless: bool = False
    browser_profile_root: Path | None = None
    browser_navigation_timeout_ms: int = Field(default=10_000, ge=1_000, le=30_000)
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
