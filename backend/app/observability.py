import logging
import os
from io import TextIOWrapper
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

from app.config import Settings

HANDLER_NAME = "gmail-unsubscribe-agent-file"


class PrivateRotatingFileHandler(RotatingFileHandler):
    """Keep the active log private each time rotation creates a new file."""

    def _open(self) -> TextIOWrapper:
        def private_opener(path: str, flags: int) -> int:
            return os.open(path, flags, 0o600)

        stream = open(  # noqa: PTH123, SIM115 - the logging handler owns the stream lifetime
            self.baseFilename,
            self.mode,
            encoding=self.encoding,
            errors=self.errors,
            opener=private_opener,
        )
        os.chmod(self.baseFilename, 0o600)
        return cast(TextIOWrapper, stream)


def configure_app_logging(settings: Settings) -> None:
    log_file = settings.log_file.resolve()
    log_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    for handler in list(app_logger.handlers):
        if handler.get_name() == HANDLER_NAME:
            app_logger.removeHandler(handler)
            handler.close()

    handler = PrivateRotatingFileHandler(
        log_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.set_name(HANDLER_NAME)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    app_logger.addHandler(handler)
    os.chmod(log_file, 0o600)


def safe_exception_stack(error: BaseException) -> str:
    frames: list[str] = []
    traceback = error.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        frames.append(
            f"{Path(frame.f_code.co_filename).name}:{traceback.tb_lineno}:{frame.f_code.co_name}"
        )
        traceback = traceback.tb_next
    return " > ".join(frames) or "unavailable"
