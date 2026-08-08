"""Database unit tests (ADR-0011 unit test category).

Verifies engine creation, session lifecycle, and the repository interface
without creating any real tables (ADR-0006: SQLite permitted for fast local
tests that do not affect behavior).
"""

from __future__ import annotations
