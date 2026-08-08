"""Sensitive-data masking for logs (ADR-0010 section 5.7).

Logs must never contain secrets, API keys, tokens, passwords, credentials,
or private authentication data. This module provides a logging filter that
masks known sensitive patterns before a record is formatted.
"""

from __future__ import annotations

import logging
import re

# Keys that, when present as "key=value", "key: value", or JSON-like
# ``"key": "value"`` pairs, identify values that must be masked.
_SENSITIVE_KEYS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "token",
    "authorization",
    "credential",
    "private_key",
    "access_token",
    "AIOS_DATABASE_PASSWORD",
)

_KEYS_ALTERNATION = "|".join(re.escape(key) for key in _SENSITIVE_KEYS)

# Matches ``key=value``, ``key: value``, ``"key": "value"`` and
# ``key = value`` forms followed by a value that must be masked.
_SENSITIVE_PATTERN = re.compile(
    rf"""(?i)(["']?(?:{_KEYS_ALTERNATION})["']?\s*[:=]\s*)(["'][^"']*["']|[^\s,;]+)"""
)

_REDACTED = "[REDACTED]"


def mask_sensitive(message: str) -> str:
    """Return ``message`` with sensitive values replaced by ``[REDACTED]``."""
    return _SENSITIVE_PATTERN.sub(rf"\g<1>{_REDACTED}", message)


class SensitiveDataFilter(logging.Filter):
    """Logging filter that masks sensitive values in emitted records.

    The mask is applied to the formatted message so that credentials never
    reach any handler (ADR-0010 section 5.7, ADR-0008 section 5.4).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive(str(record.getMessage()))
        record.args = ()
        return True
