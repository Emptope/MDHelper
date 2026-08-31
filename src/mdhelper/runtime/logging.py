"""Best-effort local diagnostic logging."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from platformdirs import user_log_path

LOGGER_NAME = "mdhelper"


def log_path(environment: dict[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    override = env.get("MDHELPER_LOG")
    if override:
        return Path(override).expanduser()
    return Path(user_log_path("MDHelper", appauthor=False, ensure_exists=False)) / "mdhelper.log"


def configure_logging(path: str | Path | None = None) -> Path | None:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        handler = logger.handlers[0]
        return Path(handler.baseFilename) if isinstance(handler, logging.FileHandler) else None
    target = log_path() if path is None else Path(path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(target, encoding="utf-8")
    except OSError:
        logger.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return target.resolve()


def record_error(error: BaseException, context: str) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        configure_logging()
    logger.error(
        "%s: %s: %s",
        context,
        type(error).__name__,
        error,
        exc_info=(type(error), error, error.__traceback__),
    )
