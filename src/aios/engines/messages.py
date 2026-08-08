"""Standardized engine message models (AIOS-605 sections 11 and 12).

Engines communicate using standardized data models (AIOS-605 section 12).
Every message carries the Engine ID, Timestamp, Input version, Output
version, Confidence, and Processing duration mandated by the framework.
Direct engine-to-engine data modification is prohibited; outputs are
consumed only through these models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aios.engines.types import EngineType


class EngineInput(BaseModel):
    """Standardized input consumed by an engine (AIOS-605 section 12).

    Engines consume standardized data only and remain independent of data
    providers (AIOS-605 section 13). The input carries the request
    identifier, the standardized payload, and the input schema version.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    input_version: str = "1.0.0"

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_id must not be empty")
        return value.strip()


class EngineOutput(BaseModel):
    """Standardized output produced by an engine (AIOS-605 sections 11 and 12).

    The output identifies the producing engine, the input and output schema
    versions, the confidence of the result, the processing duration, and the
    timestamp of completion, satisfying the AIOS-605 section 12 message
    contract.
    """

    model_config = ConfigDict(extra="forbid")

    engine_type: EngineType
    engine_id: str
    request_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    input_version: str = "1.0.0"
    output_version: str = "1.0.0"
    processing_duration: float = Field(default=0.0, ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
