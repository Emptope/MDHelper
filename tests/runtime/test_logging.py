import logging
from pathlib import Path

from mdhelper.runtime.logging import (
    LOGGER_NAME,
    configure_logging,
    log_path,
    record_command,
    record_error,
)


def _close_handlers(logger: logging.Logger) -> None:
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_log_path_override_and_error_record(tmp_path: Path) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    _close_handlers(logger)
    path = tmp_path / "diagnostics" / "mdhelper.log"
    try:
        assert log_path({"MDHELPER_LOG": str(path)}) == path
        assert configure_logging(path) == path.resolve()
        record_command("gmx rdf -f trajectory.xtc", tmp_path)
        record_error(ValueError("diagnostic detail"), "test operation")
        for handler in logger.handlers:
            handler.flush()
        content = path.read_text(encoding="utf-8")
        assert "test operation" in content
        assert "ValueError: diagnostic detail" in content
        assert "gmx rdf -f trajectory.xtc" in content
        assert f"cwd={tmp_path}" in content
    finally:
        _close_handlers(logger)
