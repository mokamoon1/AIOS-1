# ADR-0011: Testing Strategy and Quality Gates

## Document Information

- **ADR ID:** ADR-0011
- **Title:** Testing Strategy and Quality Gates
- **Status:** ACCEPTED
- **Date:** 2026-08-07
- **Decision Type:** Architecture Decision
- **Category:** Testing and Quality Decision
- **Decision Owner:** AIOS Project Owner
- **Approval Authority:** AIOS Governance Authority
- **Implementation Status:** Pending Implementation
- **Version:** 1.0.0


# 1. Context

AIOS has completed its foundational architecture decisions through ADR-0001 to ADR-0010.

The project has defined:

- Database architecture and migration strategy (ADR-0001, ADR-0006)
- Decision authority model (ADR-0002)
- Project structure alignment (ADR-0003)
- AI intelligence boundaries (ADR-0004)
- Event communication architecture (ADR-0005)
- Development toolchain (ADR-0007)
- Application foundation for configuration and logging (ADR-0008)
- Configuration and environment management (ADR-0009)
- Logging and observability foundation (ADR-0010)

ADR-0007 established pytest as the testing tool and defined pre-commit validation and CI baseline requirements.

ADR-0006 established PostgreSQL as the primary database with SQLite permitted only for fast local tests that do not affect behavior.

ADR-0010 established the logging foundation that supports test reporting and observability.

AIOS-701 through AIOS-708 define the testing strategy, unit testing, integration testing, system testing, performance testing, security testing, backtesting, and acceptance testing.

AIOS-1105 defines the testing directory structure with unit, integration, performance, security, regression, and reports directories.

Before starting Phase 1 coding, AIOS requires a unified testing strategy and explicit quality gates to control code merging.


# 2. Problem Statement

The AIOS documentation defines testing categories and a directory structure, but does not define:

- A unified testing policy applied consistently across all modules.
- Quality gates enforced before code merging.
- A clear separation of test categories and their responsibilities.
- Coverage requirements and how they are verified.
- Rules for test data isolation.
- How test results and coverage reports are stored and reviewed.

Without these decisions, teams may merge untested code, apply inconsistent testing practices, and fail to prevent regressions.


# 3. Decision Drivers

The decision is driven by:

1. Reliability of delivered code.
2. Maintainability of the codebase.
3. Regression prevention.
4. CI automation support.
5. Fast developer feedback.
6. Architecture compliance.
7. Consistency with ADR-0006, ADR-0007, and ADR-0010.


# 4. Alternatives Considered

## Alternative 1: No Formal Testing Strategy

Description:

Rely on ad hoc manual verification without a defined testing policy.

Advantages:

- No upfront investment.

Disadvantages:

- High regression risk.
- No quality guarantees.
- Contradicts AIOS governance principles.

Decision:

Rejected.

## Alternative 2: Manual Testing Only

Description:

Use manual testing exclusively without automated tests.

Advantages:

- Simple to understand.

Disadvantages:

- Slow and error prone.
- No CI automation possible.
- Poor regression prevention.

Decision:

Rejected.

## Alternative 3: pytest-Based Strategy

Description:

Adopt pytest as the single official testing framework for all test categories.

Advantages:

- Consistent with ADR-0007.
- Single tooling and configuration.
- Rich plugin ecosystem.
- Fast local execution.

Disadvantages:

- Requires disciplined test organization.

Decision:

Accepted.

## Alternative 4: Multiple Test Frameworks

Description:

Use a different framework for each test category.

Advantages:

- Specialized tools per category.

Disadvantages:

- Fragmented tooling.
- Higher configuration and learning cost.
- Inconsistent reporting.

Decision:

Rejected.

## Alternative 5: External QA Only

Description:

Delegate all testing to an external QA team without in-repository automated tests.

Advantages:

- Offloads testing effort.

Disadvantages:

- Slow feedback loop.
- No developer-owned quality gates.
- Poor integration with CI.

Decision:

Rejected.


# 5. Decision

## 5.1 Testing Framework

pytest is the official testing framework for AIOS, consistent with ADR-0007.

All test categories use pytest with a single configuration defined in the project configuration established by ADR-0007.

## 5.2 Test Categories

AIOS defines the following test categories:

- Unit Tests.
- Integration Tests.
- Database Tests.
- Event Bus Tests.
- Security Tests.
- Performance Tests.
- Regression Tests.

System Tests, Backtesting Tests, and Acceptance Tests, defined in AIOS-701 through AIOS-708, are executed within the pytest framework and classified by their nature into the appropriate categories above.

Database Tests and Event Bus Tests follow the approved testing structure defined in AIOS-1105 and do not create an independent structure outside it.

Each category has a defined responsibility and directory, consistent with AIOS-1105.

## 5.3 Test Database

PostgreSQL compatibility is required for database tests.

SQLite is permitted only for fast local tests when it does not affect behavior, consistent with ADR-0006.

## 5.4 Coverage

Coverage is measured for every code change.

An initial coverage threshold is established as a baseline and may be revised later only through a documented decision.

Baseline thresholds shall be recorded in the project configuration so they are enforceable and auditable.

## 5.5 CI Quality Gates

Merging code requires all quality gates to pass:

- Tests pass.
- Lint pass.
- Formatting pass.
- Type checking pass.
- Security checks according to stage.

These gates align with the pre-commit and CI baseline defined in ADR-0007.

## 5.6 Test Data

Real production data must not be used in tests.

Test data must be isolated and controlled per environment, consistent with the environment separation defined in ADR-0009.

## 5.7 Reporting

Test results and coverage reports are saved for every test run.

Reports must be reviewable and retained to support audit and continuous improvement.

## 5.8 Relationship with ADRs

This decision complies with:

- ADR-0006 for test database policy.
- ADR-0007 for testing framework, pre-commit validation, and CI baseline.
- ADR-0010 for logging and reporting support.


# 6. Consequences

## Positive Consequences

- Consistent testing practices across all modules.
- Enforced quality gates before merging.
- Strong regression prevention.
- CI automation readiness.
- Clear separation of test responsibilities.

## Negative Consequences

- Test infrastructure setup is required.
- Quality gates add time to the merge process.
- Coverage thresholds require ongoing maintenance.

## Risks

- Coverage thresholds may be gamed without behavioral tests.
- SQLite tests may mask PostgreSQL-specific behavior.
- Strict gates may slow delivery if not calibrated.


# 7. Related Documents

- ADR-0006 Database Migration and Initial Schema
- ADR-0007 Development Toolchain
- ADR-0010 Logging and Observability Foundation
- AIOS-701 Testing Strategy
- AIOS-702 Unit Testing
- AIOS-703 Integration Testing
- AIOS-704 System Testing
- AIOS-705 Performance Testing
- AIOS-706 Security Testing
- AIOS-707 Backtesting Framework
- AIOS-708 Acceptance Testing
- AIOS-1105 File and Folder Standards


# 8. Change Log

| Version | Change |
|---|---|
| 1.0.0 | Initial proposal for Testing Strategy and Quality Gates |
| 1.0.1 | Clarified test category mapping and alignment with AIOS-1105. |
| 1.0.2 | ADR formally accepted after governance review. |


**ADR Status:** ACCEPTED
