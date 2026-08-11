"""Provider configuration models and registry (AIOS-603 section 6, AIOS-104 section 5.2).

Defines the configuration schema for data providers and validates that only
approved provider types are used in each environment.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from aios.config.settings import Environment


class ProviderType(str, Enum):
    """Supported provider types.

    Only mock providers are permitted in Paper Trading environment.
    Live providers require explicit ADR approval and are not implemented in Phase 7.
    """

    MOCK_MARKET = "mock_market"
    MOCK_SHARIAH = "mock_shariah"
    MOCK_FUNDAMENTAL = "mock_fundamental"
    MOCK_NEWS = "mock_news"

    @classmethod
    def mock_types(cls) -> set["ProviderType"]:
        """Return the set of mock provider types allowed in Paper environment."""
        return {
            cls.MOCK_MARKET,
            cls.MOCK_SHARIAH,
            cls.MOCK_FUNDAMENTAL,
            cls.MOCK_NEWS,
        }

    @classmethod
    def is_mock(cls, provider_type: "ProviderType") -> bool:
        """Check if a provider type is a mock provider."""
        return provider_type in cls.mock_types()


class ProviderConfig(BaseModel):
    """Configuration for a single data provider.

    Each provider entry specifies its type and any type-specific options.
    No secrets (API keys, tokens) are permitted in configuration files.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: ProviderType = Field(
        description="Provider type identifier (e.g., mock_market, mock_shariah, mock_fundamental)"
    )
    enabled: bool = Field(default=True, description="Whether this provider is enabled")
    # Type-specific options can be added here as needed
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration options",
    )

    @field_validator("options")
    @classmethod
    def options_must_not_contain_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Ensure no secret keys are present in options."""
        secret_keys = {"api_key", "secret", "token", "password", "access_key", "private_key"}
        for key in value:
            if key.lower() in secret_keys:
                raise ValueError(
                    f"Secret key {key!r} is not allowed in provider configuration. "
                    f"Secrets must be provided via environment variables only."
                )
        return value


class ProvidersConfig(BaseModel):
    """Complete providers configuration section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    providers: list[ProviderConfig] = Field(
        default_factory=list,
        description="List of configured data providers",
    )

    def get_enabled_providers(self) -> list[ProviderConfig]:
        """Return only enabled provider configurations."""
        return [p for p in self.providers if p.enabled]

    def get_mock_providers(self) -> list[ProviderConfig]:
        """Return only mock provider configurations."""
        return [p for p in self.providers if ProviderType.is_mock(p.type)]

    def validate_for_environment(self, environment: "Environment") -> None:
        """Validate provider configuration for the given environment.

        In PAPER environment, only mock providers are allowed.
        """
        # Import here to avoid circular import at runtime
        from aios.config.settings import Environment

        if environment is not Environment.PAPER:
            return

        for provider in self.get_enabled_providers():
            if not ProviderType.is_mock(provider.type):
                raise ValueError(
                    f"Provider type {provider.type.value!r} is not allowed in PAPER environment. "
                    f"Only mock providers are permitted: "
                    f"{', '.join(t.value for t in ProviderType.mock_types())}"
                )