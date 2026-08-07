# AIOS-1103_NAMING_CONVENTIONS

## Document Information

**Document ID:** AIOS-1103
**Title:** Naming Conventions
**Version:** 1.0.0
**Status:** APPROVED
**Category:** Appendix

---

# 1. Purpose

This document defines the official naming conventions for AIOS.

The objective is to establish a consistent, predictable, and maintainable naming system across source code, documentation, databases, APIs, infrastructure, configuration files, and project assets.

Every identifier shall follow these conventions unless explicitly documented otherwise.

---

# 2. Objectives

The Naming Conventions shall:

* Improve readability.
* Eliminate ambiguity.
* Standardize terminology.
* Simplify maintenance.
* Support automation.
* Preserve architectural consistency.

---

# 3. General Naming Principles

All names shall be:

* Descriptive.
* Concise.
* Consistent.
* English only.
* Free of abbreviations unless officially defined.
* Free of spaces.
* Stable over time.

Names shall describe purpose rather than implementation.

---

# 4. Project Naming

Official project name:

```text
AIOS
```

Repository example:

```text
aios
```

Root directory:

```text
AI_BRAIN/
```

---

# 5. Directory Naming

Directories shall use:

```text
UPPER_SNAKE_CASE
```

Example:

```text
00_PROJECT

01_ARCHITECTURE

02_DOMAIN

03_REQUIREMENTS

04_DESIGN

05_DATA

06_DEVELOPMENT

07_TESTING

08_DEPLOYMENT

09_GOVERNANCE

110_APPENDIX
```

---

# 6. Documentation Naming

Official format:

```text
AIOS-XXXX_DOCUMENT_NAME.md
```

Examples:

```text
AIOS-101_PROJECT_CHARTER.md

AIOS-401_SYSTEM_DESIGN.md

AIOS-907_AUDIT_POLICY.md

AIOS-1101_GLOSSARY.md
```

Document IDs shall never be reused.

---

# 7. Python File Naming

Python modules shall use:

```text
snake_case.py
```

Examples:

```text
analysis_engine.py

market_structure.py

risk_manager.py

broker_service.py

signal_generator.py
```

---

# 8. Class Naming

Classes shall use:

```text
PascalCase
```

Examples:

```text
AnalysisEngine

BrokerService

MarketAnalyzer

RiskManager

PortfolioManager

ExecutionAgent
```

Class names shall represent nouns.

---

# 9. Function Naming

Functions shall use:

```text
snake_case
```

Examples:

```text
calculate_signal()

load_configuration()

execute_trade()

validate_strategy()

generate_report()
```

Function names shall begin with verbs whenever practical.

---

# 10. Variable Naming

Variables shall use:

```text
snake_case
```

Examples:

```text
market_price

current_position

risk_score

analysis_result

portfolio_value
```

Boolean variables shall begin with:

```text
is_

has_

can_

should_
```

Examples:

```text
is_valid

has_position

can_trade

should_exit
```

---

# 11. Constant Naming

Constants shall use:

```text
UPPER_SNAKE_CASE
```

Examples:

```text
MAX_RISK_PERCENT

DEFAULT_TIMEFRAME

API_TIMEOUT

MAX_POSITION_SIZE
```

---

# 12. Enumeration Naming

Enums shall use:

```text
PascalCase
```

Enum values shall use:

```text
UPPER_SNAKE_CASE
```

Example:

```text
OrderStatus

PENDING

FILLED

CANCELLED

REJECTED
```

---

# 13. Interface Naming

Interfaces shall use:

```text
PascalCase
```

Preferred suffix:

```text
Interface
```

Examples:

```text
BrokerInterface

ProviderInterface

StrategyInterface
```

---

# 14. API Naming

REST endpoints shall use:

```text
lowercase-with-hyphens
```

Examples:

```text
/api/v1/orders

/api/v1/portfolio

/api/v1/strategies

/api/v1/signals
```

HTTP methods shall follow REST standards.

---

# 15. Database Naming

Database names:

```text
snake_case
```

Example:

```text
aios_db
```

Tables:

```text
snake_case
```

Examples:

```text
market_data

trade_orders

portfolio_positions

audit_logs

risk_events
```

Columns:

```text
snake_case
```

Primary key:

```text
id
```

Foreign keys:

```text
<entity>_id
```

Example:

```text
portfolio_id

strategy_id

broker_id
```

---

# 16. Configuration Naming

Environment variables shall use:

```text
UPPER_SNAKE_CASE
```

Examples:

```text
DATABASE_URL

ALPACA_API_KEY

ALPACA_SECRET_KEY

LOG_LEVEL

PAPER_TRADING

MAX_OPEN_POSITIONS
```

---

# 17. Branch Naming

Git branches shall follow:

```text
feature/<name>

bugfix/<name>

hotfix/<name>

release/<version>

docs/<topic>

refactor/<module>

test/<scope>
```

Examples:

```text
feature/market-analysis

bugfix/order-validation

release/v1.2.0
```

---

# 18. ADR Naming

Architectural Decision Records:

```text
ADR-0001-title.md
```

Examples:

```text
ADR-0001-project-architecture.md

ADR-0002-provider-abstraction.md

ADR-0003-risk-engine.md
```

ADR numbers shall never change.

---

# 19. Logging Names

Logger names shall follow module names.

Examples:

```text
analysis

broker

execution

portfolio

security

api
```

---

# 20. Future Expansion

Future naming standards may include:

* Kubernetes resources.
* Cloud infrastructure.
* AI model naming.
* Event naming.
* Message queue naming.
* Distributed services.

The naming convention shall evolve while preserving backward consistency.

---

# 21. Success Criteria

The Naming Conventions are considered successful when:

* Every identifier is predictable.
* Naming remains consistent across the project.
* Code readability improves.
* Documentation aligns with implementation.
* Automated tooling can rely on standardized names.

---

# 22. Document Status

**Document ID:** AIOS-1103_NAMING_CONVENTIONS

**Version:** 1.0.0

**Status:** APPROVED
