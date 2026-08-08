"""Shariah repository (AIOS-606, AIOS-504).

Compliance history is immutable: every provider review is appended as a new
record (AIOS-504 section 9, AIOS-507). The repository serves the latest
effective compliance record for a symbol.
"""

from __future__ import annotations

from datetime import date
from typing import cast

from sqlalchemy import select

from aios.data.models import ShariahCompliance
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import ShariahSecurityModel
from aios.database.repositories.base import BaseRepository


class ShariahRepository(BaseRepository[ShariahSecurityModel]):
    """Repository for Shariah compliance records."""

    entity_type = ShariahSecurityModel

    def add_records(self, records: list[ShariahCompliance]) -> int:
        """Append compliance records as new immutable rows."""
        if not records:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            for record in records:
                session.add(
                    ShariahSecurityModel(
                        symbol=record.symbol,
                        company_name=record.company_name,
                        exchange=record.exchange,
                        country=record.country,
                        asset_type=record.asset_type,
                        compliance_status=record.compliance_status,
                        provider=record.provider,
                        provider_version=record.provider_version,
                        review_date=record.review_date,
                        effective_date=record.effective_date,
                        expiration_date=record.expiration_date,
                        screening_methodology=record.screening_methodology,
                        screening_version=record.screening_version,
                        screening_date=record.screening_date,
                        confidence_level=record.confidence_level,
                        previous_status=record.previous_status,
                        retrieval_timestamp=record.retrieval_timestamp,
                    )
                )
                stored += 1
        return stored

    def get_compliance_status(self, symbol: str, *, as_of: date | None = None) -> ShariahCompliance:
        """Return the latest compliance record effective on/before ``as_of``.

        Without ``as_of`` the latest effective record is returned. Raises
        :class:`RecordNotFoundError` when no record exists.
        """
        statement = select(ShariahSecurityModel).where(ShariahSecurityModel.symbol == symbol)
        if as_of is not None:
            statement = statement.where(ShariahSecurityModel.effective_date <= as_of)
        row = self._first(
            statement.order_by(
                ShariahSecurityModel.effective_date.desc(),
                ShariahSecurityModel.retrieval_timestamp.desc(),
            )
        )
        if row is None:
            raise RecordNotFoundError(f"No compliance record for {symbol!r} as of {as_of}")
        return cast(ShariahSecurityModel, row).to_domain()
