import logging
from pathlib import Path

from mdhelper.runtime.logging import LOGGER_NAME, configure_logging, log_path, record_error


def test_log_path_override_and_error_record(tmp_path: Path) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    path = tmp_path / "diagnostics" / "mdhelper.log"
    assert log_path({"MDHELPER_LOG": str(path)}) == path
    assert configure_logging(path) == path.resolve()
    record_error(ValueError("diagnostic detail"), "test operation")
    for handler in logger.handlers:
        handler.flush()
    content = path.read_text(encoding="utf-8")
    assert "test operation" in content
    assert "ValueError: diagnostic detail" in content
