# ADR-0001: Database Selection

## Document Information

**ADR ID:** ADR-0001
**Title:** Database Selection
**Status:** Accepted
**Date:** 2026-08-07
**Decision Type:** Architecture Decision

---

# 1. Context

AIOS requires a reliable data storage system to support:

* Historical market data.
* Shariah compliance records.
* Company fundamentals.
* Technical and fundamental analysis results.
* Investment decisions.
* Portfolio management.
* Risk calculations.
* System audit logs.
* AI agent memory.

The original documentation contained conflicting database recommendations:

* AIOS-402_DATABASE_DESIGN suggested SQLite for version 1.
* AIOS-1106_TECHNOLOGY_STACK identified PostgreSQL as the primary database technology.

A final decision is required before implementation begins.

---

# 2. Decision

AIOS will use:

# PostgreSQL as the primary database system

with:

* SQLAlchemy as the ORM/database abstraction layer.
* Migration support through a database migration tool.
* Repository Pattern for database access.

SQLite may only be used for:

* Local unit tests.
* Temporary development environments.
* Lightweight experiments.

SQLite is not considered the production database architecture.

---

# 3. Reasons for Decision

## 3.1 Scalability

AIOS is designed to manage:

* Large historical datasets.
* Multiple analysis results.
* Decision history.
* Portfolio records.
* AI memory.

PostgreSQL provides better scalability for future growth.

---

## 3.2 Data Integrity

AIOS requires strong consistency for:

* Investment decisions.
* Compliance records.
* Audit trails.
* Portfolio information.

PostgreSQL provides advanced transactional guarantees.

---

## 3.3 Future Expansion

Future AIOS versions may require:

* Multiple markets.
* Multiple brokers.
* Multiple users.
* Cloud deployment.
* Advanced analytics.

PostgreSQL supports these requirements.

---

## 3.4 Architecture Alignment

This decision aligns with:

* AIOS-1106 Technology Stack.
* AIOS-501 Data Architecture.
* AIOS-507 Data Storage.

---

# 4. Database Architecture

The database layer shall follow:

```
Application Layer

        ↓

Repository Layer

        ↓

SQLAlchemy

        ↓

PostgreSQL Database
```

Direct database access from business modules is prohibited.

---

# 5. Logical Database Domains

AIOS database shall contain logical domains:

## Shariah Database Domain

Stores:

* Securities compliance status.
* Provider information.
* Compliance history.

---

## Market Database Domain

Stores:

* OHLCV data.
* Market events.
* Historical prices.

---

## Company Database Domain

Stores:

* Financial statements.
* Company metrics.
* Valuation data.

---

## Analysis Database Domain

Stores:

* Technical analysis.
* Fundamental analysis.
* Signals.

---

## Portfolio Database Domain

Stores:

* Positions.
* Allocation.
* Performance.

---

## Decision Database Domain

Stores:

* Investment decisions.
* Reasoning.
* Confidence scores.

---

## System Database Domain

Stores:

* Logs.
* Events.
* Configuration history.

---

# 6. Consequences

## Positive Consequences

* Better scalability.
* Stronger data integrity.
* Production-ready architecture.
* Better support for AI memory and analytics.
* Easier future cloud migration.

---

## Negative Consequences

* Higher setup complexity compared with SQLite.
* Requires database server management.
* Requires migration strategy.

---

# 7. Implementation Rules

Developers and AI agents must:

* Use SQLAlchemy for database interaction.
* Avoid direct SQL access from business logic.
* Create migrations for schema changes.
* Maintain database documentation.
* Include database tests.

---

# 8. Related Documents

* AIOS-402_DATABASE_DESIGN
* AIOS-501_DATA_ARCHITECTURE
* AIOS-507_DATA_STORAGE
* AIOS-1106_TECHNOLOGY_STACK
* AIOS-1108_AI_DEVELOPMENT_GUIDELINES

---

# 9. Final Decision

**Approved Decision:**

AIOS uses PostgreSQL as the primary database architecture.

SQLite is limited to testing and lightweight development only.

---

**ADR Status:** ACCEPTED
