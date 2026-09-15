import pytest

from app import main
from app.config import Settings


@pytest.fixture(autouse=True)
def isolate_app_factory_defaults_from_real_credentials(monkeypatch, tmp_path) -> None:
    def test_settings() -> Settings:
        return Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path / 'api.db'}",
            log_file=tmp_path / "logs" / "unsubscribe.log",
            google_client_secrets_file=None,
            browser_profile_root=tmp_path / "browser-profiles",
        )

    monkeypatch.setattr(main, "Settings", test_settings)
