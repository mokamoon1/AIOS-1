"""Company fundamentals repository (AIOS-606, AIOS-502 section 6)."""

from __future__ import annotations

from datetime import date
from typing import cast

from sqlalchemy import select

from aios.data.models import CompanyFundamentals
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import CompanyFundamentalModel
from aios.database.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[CompanyFundamentalModel]):
    """Repository for company financial information."""

    entity_type = CompanyFundamentalModel

    def add_fundamentals(self, records: list[CompanyFundamentals]) -> int:
        """Append fundamentals records as new immutable rows."""
        if not records:
            return 0
        stored = 0
        with session_scope(self._session_factory) as session:
            for record in records:
                session.add(
                    CompanyFundamentalModel(
                        symbol=record.symbol,
                        sector=record.sector,
                        industry=record.industry,
                        revenue=record.revenue,
                        net_income=record.net_income,
                        eps=record.eps,
                        assets=record.assets,
                        liabilities=record.liabilities,
                        cash_flow=record.cash_flow,
                        equity=record.equity,
                        report_date=record.report_date,
                        retrieval_timestamp=record.retrieval_timestamp,
                    )
                )
                stored += 1
        return stored

    def get_fundamentals(
        self, symbol: str, *, report_date: date | None = None
    ) -> CompanyFundamentals:
        """Return the latest fundamentals for ``symbol``.

        Without ``report_date`` the most recent report is returned. Raises
        :class:`RecordNotFoundError` when no report exists.
        """
        statement = select(CompanyFundamentalModel).where(CompanyFundamentalModel.symbol == symbol)
        if report_date is not None:
            statement = statement.where(CompanyFundamentalModel.report_date == report_date)
        row = self._first(statement.order_by(CompanyFundamentalModel.report_date.desc()))
        if row is None:
            raise RecordNotFoundError(f"No fundamentals for {symbol!r}")
        return cast(CompanyFundamentalModel, row).to_domain()
