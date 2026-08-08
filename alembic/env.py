"""Alembic environment for AIOS (ADR-0006).

Connects Alembic to the SQLAlchemy declarative Base and reads the database
URL from the AIOS configuration module (ADR-0009). The migration target is
``Base.metadata`` so that every AIOS ORM model is tracked by migrations.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from aios.config import ConfigError, load_settings
from aios.database.base import Base

# Import all ORM models so they register on Base.metadata (ADR-0006). Alembic
# autogenerate and ``alembic check`` compare against the full metadata.
import aios.database.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

try:
    settings = load_settings()
except ConfigError:
    settings = None


def _database_url() -> str:
    """Return the database URL from AIOS settings.

    Falls back to the value in alembic.ini only when AIOS configuration
    cannot be resolved, so migrations still work without a full runtime
    configuration while never requiring credentials in this file.
    """
    if settings is not None:
        return settings.database.database_url
    return config.get_main_option("sqlalchemy.url", "")


def run_migrations_offline() -> None:
    """Run migrations in offline mode (no DBAPI connection)."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode (real database connection)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
