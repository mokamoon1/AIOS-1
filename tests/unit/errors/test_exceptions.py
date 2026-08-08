"""Unified exception hierarchy tests (AIOS-104 section 7)."""

from __future__ import annotations

import pytest

from aios.config.errors import ConfigError
from aios.database.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    RecordNotFoundError,
)
from aios.errors import (
    AgentError,
    AiosError,
    ConfigurationError,
    DataError,
    EventBusError,
    ProviderError,
    SecurityError,
    WorkflowError,
)
from aios.errors import (
    DatabaseError as RootDatabaseError,
)
from aios.events.exceptions import EventValidationError

pytestmark = pytest.mark.unit


class TestAiosErrorHierarchy:
    def test_root_error_is_base(self) -> None:
        assert issubclass(AiosError, Exception)

    @pytest.mark.parametrize(
        "error_type",
        [
            ConfigurationError,
            DatabaseError,
            EventBusError,
            AgentError,
            ProviderError,
            WorkflowError,
            SecurityError,
            DataError,
        ],
    )
    def test_domain_errors_inherit_root(self, error_type: type) -> None:
        assert issubclass(error_type, AiosError)

    def test_config_error_inherits_configuration_error(self) -> None:
        assert issubclass(ConfigError, ConfigurationError)
        assert issubclass(ConfigError, AiosError)

    def test_database_errors_inherit_root(self) -> None:
        assert issubclass(DatabaseError, AiosError)
        assert issubclass(DatabaseConnectionError, AiosError)
        assert issubclass(RecordNotFoundError, AiosError)
        assert DatabaseError is RootDatabaseError

    def test_event_errors_inherit_root(self) -> None:
        assert issubclass(EventBusError, AiosError)
        assert issubclass(EventValidationError, EventBusError)
        assert issubclass(EventValidationError, AiosError)

    def test_existing_catch_still_works(self) -> None:
        with pytest.raises(ConfigError):
            raise ConfigError("bad config")

    def test_catch_via_root(self) -> None:
        with pytest.raises(AiosError):
            raise ProviderError("provider down")
