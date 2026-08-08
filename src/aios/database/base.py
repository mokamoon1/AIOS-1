"""Declarative base for all AIOS ORM models (ADR-0001, ADR-0006).

Database models, names, and columns follow snake_case per AIOS-1103. The
initial schema is created through an initial Alembic migration and is never
auto-created by the ORM in production (ADR-0006 section 5.3).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for all AIOS ORM models.

    Naming conventions align with AIOS-1103: tables and columns use
    snake_case, primary keys are named ``id``, and foreign keys are named
    ``<entity>_id`` (ADR-0006 section 5.3).
    """
