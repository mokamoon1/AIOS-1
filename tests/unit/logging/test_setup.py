"""Logging bootstrap tests (ADR-0010 sections 5.1 and 5.2).

Verifies that ``setup_logging`` selects the correct formatter and
destination based on the environment configuration.
"""

from __future__ import annotations

import io
import logging
import logging.handlers

import pytest

from aios.config.settings import LoggingDestination, LoggingFormat, LoggingSettings
from aios.logging.formatters import HumanReadableFormatter, JsonFormatter
from aios.logging.setup import _build_handler, setup_logging

pytestmark = pytest.mark.unit


class TestLoggingSettings:
    def test_defaults(self) -> None:
        settings = LoggingSettings()
        assert settings.level == "INFO"
        assert settings.format is LoggingFormat.HUMAN
        assert settings.destination is LoggingDestination.CONSOLE
        assert settings.file_path == "logs/aios.log"

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_supported_levels(self, level: str) -> None:
        assert LoggingSettings(level=level).level == level

    @pytest.mark.parametrize("level", ["TRACE", "NOTICE", "verbose"])
    def test_unsupported_level_rejected(self, level: str) -> None:
        with pytest.raises(ValueError, match="Unsupported logging level"):
            LoggingSettings(level=level)

    def test_env_variable_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_LOGGING_LEVEL", "DEBUG")
        settings = LoggingSettings()
        assert settings.level == "DEBUG"


class TestBuildHandler:
    def test_console_handler_uses_human_formatter(self) -> None:
        handler = _build_handler(LoggingSettings())
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, HumanReadableFormatter)

    def test_file_handler_rotates_and_uses_json(self) -> None:
        handler = _build_handler(
            LoggingSettings(
                format=LoggingFormat.JSON,
                destination=LoggingDestination.FILE,
                file_path="logs/aios.log",
            )
        )
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert isinstance(handler.formatter, JsonFormatter)

    def test_handlers_mount_security_filters(self) -> None:
        handler = _build_handler(LoggingSettings())
        from aios.logging.correlation import CorrelationFilter
        from aios.logging.masking import SensitiveDataFilter

        filter_types = {type(f) for f in handler.filters}
        assert SensitiveDataFilter in filter_types
        assert CorrelationFilter in filter_types


class TestSetupLogging:
    def test_configured_root_logger(self) -> None:
        root = setup_logging(LoggingSettings(level="INFO"))
        assert root.name == "aios"
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        root.handlers = []

    def test_emits_to_stream(self) -> None:
        stream = io.StringIO()
        root = setup_logging(LoggingSettings())
        root.handlers[0].stream = stream
        root.info("bootstrap complete")
        root.handlers = []
        assert "bootstrap complete" in stream.getvalue()
