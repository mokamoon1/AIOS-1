"""Database repositories package (AIOS-606).

Concrete SQLAlchemy-backed repositories implement the Repository protocol
(AIOS-606 section 5) and the EventRepository protocol (ADR-0005 section
5.5). No module outside the Database Layer communicates with the database.
"""

from aios.database.repositories.analysis import AnalysisRepository
from aios.database.repositories.broker_account import BrokerAccountRepository
from aios.database.repositories.company import CompanyRepository
from aios.database.repositories.decision import DecisionRepository
from aios.database.repositories.event_log import EventLogRepository
from aios.database.repositories.market import MarketRepository
from aios.database.repositories.paper_fill import PaperFillRepository
from aios.database.repositories.paper_order import PaperOrderRepository
from aios.database.repositories.paper_position import PaperPositionRepository
from aios.database.repositories.portfolio import PortfolioRepository
from aios.database.repositories.shariah import ShariahRepository

__all__ = [
    "AnalysisRepository",
    "BrokerAccountRepository",
    "CompanyRepository",
    "DecisionRepository",
    "EventLogRepository",
    "MarketRepository",
    "PaperFillRepository",
    "PaperOrderRepository",
    "PaperPositionRepository",
    "PortfolioRepository",
    "ShariahRepository",
]
