"""Broker account repository (AIOS-606, AIOS-407 section 4.3).

Stores the current paper account status ("Check Account" operation). The
account is upserted by broker identifier.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import select

from aios.brokers.models import BrokerAccount
from aios.database.engine import session_scope
from aios.database.exceptions import RecordNotFoundError
from aios.database.models import BrokerAccountModel
from aios.database.repositories.base import BaseRepository


class BrokerAccountRepository(BaseRepository[BrokerAccountModel]):
    """Repository for the paper broker account (AIOS-407)."""

    entity_type = BrokerAccountModel

    def upsert_account(self, account: BrokerAccount) -> BrokerAccount:
        """Insert or update the account for ``broker_id``."""
        with session_scope(self._session_factory) as session:
            model = session.scalars(
                select(BrokerAccountModel).where(BrokerAccountModel.broker_id == account.broker_id)
            ).first()
            if model is None:
                model = BrokerAccountModel.from_account(account)
                session.add(model)
            else:
                model.account_id = account.account_id
                model.currency = account.currency
                model.cash = account.cash
                model.initial_cash = account.initial_cash
                model.updated_at = account.updated_at
            session.flush()
            return model.to_domain()

    def get_account(self, broker_id: str) -> BrokerAccount:
        """Return the account for ``broker_id``.

        Raises :class:`RecordNotFoundError` when no account is stored.
        """
        statement = select(BrokerAccountModel).where(BrokerAccountModel.broker_id == broker_id)
        row = self._first(statement)
        if row is None:
            raise RecordNotFoundError(f"No broker account for {broker_id!r}")
        return cast(BrokerAccountModel, row).to_domain()
