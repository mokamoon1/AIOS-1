"""Database engine creation and session factory (ADR-0001, ADR-0006).

PostgreSQL is the primary database; SQLite is permitted only for local unit
tests and lightweight development (ADR-0001, ADR-0006 section 5.2).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the given database URL.

    Args:
        database_url: SQLAlchemy connection URL, e.g. from
            :attr:`aios.config.settings.DatabaseSettings.database_url`.
        echo: Enable SQL statement logging (development only).

    Returns:
        A configured SQLAlchemy :class:`Engine`.
    """
    return create_engine(database_url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine.

    Returns:
        A :class:`sqlalchemy.orm.sessionmaker` configured for AIOS sessions.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations.

    Commits on success and rolls back on error, then always closes the
    session (AIOS-606 sections 7 and 10).

    Yields:
        An open SQLAlchemy :class:`Session`.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
