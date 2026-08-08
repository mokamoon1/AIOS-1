"""AIOS database layer package (ADR-0001, ADR-0006).

Provides the engine, session management, declarative base, repository
interface, exceptions, ORM models, and concrete repositories for the
Database Layer (AIOS-606).
"""

from __future__ import annotations

from aios.database.base import Base
from aios.database.engine import create_db_engine, create_session_factory, session_scope
from aios.database.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    DatabaseIntegrityError,
    DatabaseOperationalError,
    RecordNotFoundError,
)
from aios.database.models import (
    AnalysisResultModel,
    BrokerAccountModel,
    CompanyFundamentalModel,
    EventLogModel,
    InvestmentDecisionModel,
    MarketCandleModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
    PortfolioPositionModel,
    SecurityModel,
    ShariahSecurityModel,
)
from aios.database.repositories import (
    AnalysisRepository,
    BrokerAccountRepository,
    CompanyRepository,
    DecisionRepository,
    EventLogRepository,
    MarketRepository,
    PaperFillRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PortfolioRepository,
    ShariahRepository,
)
from aios.database.repository import Repository

__all__ = [
    "AnalysisRepository",
    "AnalysisResultModel",
    "Base",
    "BrokerAccountModel",
    "BrokerAccountRepository",
    "CompanyFundamentalModel",
    "CompanyRepository",
    "DatabaseConnectionError",
    "DatabaseError",
    "DatabaseIntegrityError",
    "DatabaseOperationalError",
    "DecisionRepository",
    "EventLogModel",
    "EventLogRepository",
    "InvestmentDecisionModel",
    "MarketCandleModel",
    "MarketRepository",
    "PaperFillModel",
    "PaperFillRepository",
    "PaperOrderModel",
    "PaperOrderRepository",
    "PaperPositionModel",
    "PaperPositionRepository",
    "PortfolioPositionModel",
    "PortfolioRepository",
    "RecordNotFoundError",
    "Repository",
    "SecurityModel",
    "ShariahRepository",
    "ShariahSecurityModel",
    "create_db_engine",
    "create_session_factory",
    "session_scope",
]
