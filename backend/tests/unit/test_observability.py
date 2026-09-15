import logging
import os
import stat

from app.config import Settings
from app.observability import configure_app_logging


def test_rotated_log_files_remain_private(tmp_path) -> None:
    log_file = tmp_path / "logs" / "unsubscribe.log"
    settings = Settings(
        _env_file=None,
        log_file=log_file,
        log_max_bytes=10_000,
        log_backup_count=2,
    )

    previous_umask = os.umask(0o022)
    try:
        configure_app_logging(settings)
        logger = logging.getLogger("app.test.rotation")
        logger.error("first %s", "x" * 11_000)
        logger.error("second %s", "y" * 11_000)
    finally:
        os.umask(previous_umask)

    assert log_file.exists()
    assert (log_file.parent / "unsubscribe.log.1").exists()
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600
    assert stat.S_IMODE((log_file.parent / "unsubscribe.log.1").stat().st_mode) == 0o600
