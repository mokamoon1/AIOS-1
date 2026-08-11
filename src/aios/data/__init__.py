"""AIOS Data Layer (AIOS-501, AIOS-505, AIOS-506).

The Data Layer standardizes all incoming information (AIOS-503 section 2),
validates it before storage (AIOS-506), and serves it to engines through a
single facade. No module outside the Data Layer accesses providers directly
(AIOS-501 section 2); storage lives behind Database Layer repositories
(AIOS-606).
"""

from aios.data.exceptions import (
    DataNotFoundError,
    DataPipelineError,
    DataValidationError,
)
from aios.data.ingestion import (
    IngestionConfig,
    IngestionService,
)
from aios.data.models import (
    AssetType,
    Candle,
    CompanyFundamentals,
    ComplianceStatus,
    CorporateAction,
    CorporateActionType,
    CorporateActionProvider,
    DecisionAction,
    HistoricalUniverseProvider,
    InvestmentDecision,
    MarketStatus,
    PointInTimeDataProvider,
    PortfolioPosition,
    PositionStatus,
    Security,
    SecurityLifecycle,
    SecurityLifecycleStatus,
    SessionStatus,
    ShariahCompliance,
    Timeframe,
)
from aios.data.pipeline import DataPipeline, PipelineRun, PipelineStage, StageMetrics
from aios.data.services import DataService
from aios.data.validation import (
    DataValidator,
    ValidationErrorCode,
    ValidationIssue,
    ValidationReport,
    ValidationResult,
    raise_for_invalid,
)

__all__ = [
    "AssetType",
    "Candle",
    "CompanyFundamentals",
    "ComplianceStatus",
    "CorporateAction",
    "CorporateActionProvider",
    "CorporateActionType",
    "DataNotFoundError",
    "DataPipeline",
    "DataPipelineError",
    "DataService",
    "DataValidationError",
    "DataValidator",
    "DecisionAction",
    "HistoricalUniverseProvider",
    "IngestionConfig",
    "IngestionService",
    "InvestmentDecision",
    "MarketStatus",
    "PipelineRun",
    "PipelineStage",
    "PointInTimeDataProvider",
    "PortfolioPosition",
    "PositionStatus",
    "Security",
    "SecurityLifecycle",
    "SecurityLifecycleStatus",
    "SessionStatus",
    "ShariahCompliance",
    "Timeframe",
    "ValidationErrorCode",
    "ValidationIssue",
    "ValidationReport",
    "ValidationResult",
    "raise_for_invalid",
]
