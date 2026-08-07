# ADR-0006: Database Migration and Initial Schema

## Document Information

**ADR ID:** ADR-0006
**Title:** Database Migration and Initial Schema
**Status:** ACCEPTED
**Date:** 2026-08-07
**Decision Type:** Architecture Decision
**Category:** Architecture Decision
**Decision Owner:** AIOS Project Owner
**Approval Authority:** AIOS Governance Authority
**Implementation Status:** Pending Implementation
**Version:** 1.0.0

---

# 1. Context

ADR-0001 establishes PostgreSQL as the primary database system, with SQLAlchemy as the ORM/database abstraction layer, Repository Pattern for database access, and migration support through a database migration tool.

ADR-0001 requires migration support but does not name the migration tool.

AIOS-1106 Technology Stack confirms PostgreSQL and SQLAlchemy but does not name a migration tool.

The AIOS documentation defines the database structure in multiple documents:

* AIOS-402 Database Design defines a modular database with tables including `shariah_securities`, `market_prices`, `company_fundamentals`, `analysis_results`, `portfolio_positions`, and `investment_decisions`.
* AIOS-501 Data Architecture defines six data domains: Market, Company, Shariah, Portfolio, Decision, and System.
* AIOS-502 Data Sources defines the required information for each data source category.
* AIOS-503 Market Data Model defines the standardized market data model including the core security entity and candle model.
* AIOS-504 Shariah Data Model defines the compliance record model including review, effective, and expiration dates, screening methodology, and confidence level.
* AIOS-505 Data Pipeline requires validation before storage and immutable historical records.
* AIOS-506 Data Validation requires multi-level validation before data enters storage.
* AIOS-507 Data Storage requires historical records to never be overwritten and defines indexing strategy.
* AIOS-606 Database Layer establishes the Repository Pattern with domain repositories including `ShariahRepository`, `MarketRepository`, `CompanyRepository`, `PortfolioRepository`, `DecisionRepository`, and `MemoryRepository`.
* ADR-0005 requires every published event to be persisted to the System Database Domain via the `EventRepository` before dispatch.

The project requires a defined migration tool, an initial schema strategy, and schema change management rules before Phase 1 database implementation begins.

---

# 2. Problem Statement

The AIOS documentation defines what must be stored but does not define the implementation details required for Phase 1:

* The migration tool is not named.
* The initial schema is not defined.
* The relationship between PostgreSQL, SQLAlchemy, and the Repository Pattern is not specified at implementation level.
* The Shariah and market data models defined in AIOS-504 and AIOS-503 must be reconciled with the simpler table definitions in AIOS-402.
* Event storage, required by ADR-0005, has no defined location.
* Schema change management rules are not established.

This ambiguity blocks Phase 1 implementation because the database layer, event persistence, and all repositories cannot be built consistently while these questions remain open.

---

# 3. Decision Drivers

The decision shall satisfy the following drivers:

* **Traceability:** Every record and schema change must remain traceable (AIOS-501, AIOS-507).
* **Immutability:** Historical records shall never be overwritten (AIOS-501, AIOS-505, AIOS-507).
* **Validation First:** No data shall enter storage without passing validation (AIOS-505, AIOS-506).
* **Repository Isolation:** No module outside the Database Layer shall communicate directly with the database (AIOS-606, ADR-0001).
* **Event Persistence:** Every event must be persisted before dispatch (ADR-0005).
* **Shariah Data Fidelity:** Compliance records must preserve provider, review date, effective and expiration dates, screening methodology, and confidence level (AIOS-504).
* **Market Data Fidelity:** Market records must preserve symbol, exchange, asset type, currency, session, and time zone (AIOS-503).
* **Naming Compliance:** Database names, tables, and columns shall follow snake_case per AIOS-1103.
* **Governance Compliance:** Schema changes shall be managed as controlled changes (AIOS-902, AIOS-906).

---

# 4. Alternatives Considered

## Alternative 1: Alembic Migration Tool

Use Alembic, the standard SQLAlchemy migration tool, for schema migrations.

### Advantages

* Natively integrates with SQLAlchemy models.
* Versioned migration history.
* Supports upgrade and downgrade operations.
* Widely used and community-supported.
* Aligns with AIOS-1106 SQLAlchemy selection.

### Disadvantages

* Requires migration files to be written and maintained.
* Requires discipline to keep models and migrations synchronized.

---

## Alternative 2: Raw SQL Migration Scripts

Use hand-written SQL scripts for schema migrations.

### Advantages

* Full control over SQL.
* No additional framework dependency.

### Disadvantages

* No built-in versioning or rollback.
* Higher risk of inconsistency with ORM models.
* Manual change tracking is error-prone.
* Contradicts the SQLAlchemy-based architecture in ADR-0001.

---

## Alternative 3: ORM Auto-Creation Without Migrations

Create the schema automatically from SQLAlchemy models at startup.

### Advantages

* Fast initial setup.
* No migration files required.

### Disadvantages

* No controlled schema evolution.
* No versioned history or downgrade path.
* Risky for production data integrity.
* Contradicts the auditability and change management requirements of AIOS-902 and AIOS-507.

---

# 5. Decision

AIOS adopts **Alembic** as the database migration tool, with an initial schema organized around the logical domains defined in ADR-0001 and AIOS-501, and governed by explicit schema change management rules.

---

## 5.1 Migration Tool

* **Alembic** is the official migration tool for AIOS.
* All schema changes shall be implemented as Alembic migrations.
* Each migration shall be versioned, reversible, and stored under version control.
* Migration files shall be reviewed as part of the change management process (AIOS-902).

---

## 5.2 PostgreSQL, SQLAlchemy, and Repository Relationship

The implementation follows a three-layer structure. Alembic operates only at development and deployment time and is not part of the runtime path:

```text
Runtime Path (application execution):

Application Modules

        ↓

Repository Layer

        ↓

SQLAlchemy ORM

        ↓

PostgreSQL Database

Development/Deployment Time (schema management only):

Alembic Migrations ─────────────► PostgreSQL Database
        (schema evolution only, not a runtime layer)
```

* **PostgreSQL** is the production database system.
* **SQLAlchemy** is the ORM/database abstraction layer; no direct SQL from business modules.
* **Repository Pattern** is the only access path for application modules (AIOS-606).
* **Alembic** is a **schema migration tool** used only at development and deployment time. It is not a runtime layer and does not participate in the application execution path; its sole role is managing schema evolution.
* SQLAlchemy models and Alembic migrations must remain synchronized.
* **SQLite** is used for tests and local development only, per ADR-0001. The test schema shall remain compatible with the Alembic definitions, and no schema differences specific to production are permitted.

---

## 5.3 Initial Schema Strategy

* The initial schema shall be organized by the logical domains defined in ADR-0001: Shariah, Market, Company, Analysis, Portfolio, Decision, and System.
* Each domain shall be represented by tables using snake_case names per AIOS-1103.
* Each table shall have a primary key named `id` and foreign keys named `<entity>_id` per AIOS-1103.
* The initial schema shall be created through an initial Alembic migration; schema is never auto-created by the ORM in production.
* Data quality, immutability, and retention requirements of AIOS-501, AIOS-505, AIOS-506, and AIOS-507 apply to all tables.

---

## 5.4 Shariah Data Model

The Shariah domain shall implement the compliance record model defined in AIOS-504:

* Compliance status with allowed values: `COMPLIANT`, `NON_COMPLIANT`, `UNDER_REVIEW`, `UNKNOWN`.
* Provider identification and provider version.
* Review date.
* Effective date.
* Expiration date.
* Screening methodology, version, and date.
* Confidence level.
* Retrieval timestamp.

Compliance history shall never be overwritten; each provider review creates a new record per AIOS-504 and AIOS-507.

---

## 5.5 Market Data Model

The Market domain shall implement the market data model defined in AIOS-503:

* Core security entity fields: Symbol, Exchange, Asset Type, Currency, Trading Session, Time Zone, Market Status.
* Candle fields: Timestamp, Open, High, Low, Close, Volume, with optional VWAP, Trade Count, and Average Price.
* Candle validation rules: Open greater than zero, High greater than or equal to Open and Close, Low less than or equal to Open and Close, Volume greater than or equal to zero, valid timestamp.
* Support for the timeframes defined in AIOS-503.
* Historical market records shall remain immutable after storage.

---

## 5.6 Event Storage

* Events published to the Event Bus shall be persisted to the System Database Domain via the `EventRepository` **before dispatch**, per ADR-0005.
* The event log table shall store the event structure defined in AIOS-103, with column names in snake_case per AIOS-1103: `event_id`, `timestamp`, `source`, `event_type`, `payload`, `priority`, and `status`.
* The event log satisfies the audit, traceability, and explainability requirements of AIOS-103 and ADR-0005.

---

## 5.7 Schema Change Management Rules

Schema changes shall follow these rules:

* Every schema change requires an Alembic migration.
* No direct manual SQL modifications to the production schema.
* Migrations shall be reviewed before application to the shared database.
* Schema changes affecting existing data shall include a data preservation plan; historical records are never overwritten (AIOS-507).
* Migration history is version controlled and immutable after application.
* Downgrade paths shall be defined where feasible.
* Schema changes affecting architecture or data governance require ADR documentation per AIOS-902.
* The initial schema is deployed through a single initial migration; subsequent changes are incremental.

---

# 6. Consequences

## Positive Consequences

* Migration tool is explicit and natively aligned with SQLAlchemy.
* Schema evolution is versioned, traceable, and reversible.
* Shariah and market models preserve the required fidelity defined in AIOS-503 and AIOS-504.
* Event persistence satisfies ADR-0005 with a defined storage location.
* Historical immutability and auditability are preserved.
* Database access remains isolated behind the Repository Pattern.

---

## Negative Consequences

* Alembic migration files add maintenance overhead.
* Initial schema design effort is required before implementation.
* Migrations require review discipline to stay synchronized with ORM models.

---

## Risks

* Divergence between SQLAlchemy models and Alembic migrations.
* Loss of data fidelity if provider-specific fields are normalized away.
* Migration failures during upgrade or downgrade.
* Incomplete event logging reducing auditability.
* Performance degradation on large historical market data without proper indexing.

These risks shall be managed through migration review, validation testing, indexing per AIOS-507, and governance oversight during development.

---

# 7. Related Documents

* AIOS-402_DATABASE_DESIGN
* AIOS-501_DATA_ARCHITECTURE
* AIOS-502_DATA_SOURCES
* AIOS-503_MARKET_DATA_MODEL
* AIOS-504_SHARIAH_DATA_MODEL
* AIOS-505_DATA_PIPELINE
* AIOS-506_DATA_VALIDATION
* AIOS-507_DATA_STORAGE
* AIOS-606_DATABASE_LAYER
* AIOS-902_DECISION_POLICY
* AIOS-1103_NAMING_CONVENTIONS
* AIOS-1106_TECHNOLOGY_STACK
* ADR-0001_DATABASE_SELECTION
* ADR-0005_EVENT_BUS_ARCHITECTURE

---

# 8. Change Log

**Version:** 1.0.0

**Change:** Initial formal ADR proposal for the database migration tool and initial schema.

---

**Version:** 1.0.1

**Change:** Event log column names restated in snake_case per AIOS-1103; clarified that Alembic is a development/deployment-time schema migration tool and not a runtime layer; clarified the SQLite test-only policy.

---

**Version:** 1.0.2

**Change:** ADR formally accepted after governance review.

---

**ADR Status:** ACCEPTED
