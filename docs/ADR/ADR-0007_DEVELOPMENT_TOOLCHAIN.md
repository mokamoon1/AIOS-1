# ADR-0007: Development Toolchain

## Document Information

- **ADR ID:** ADR-0007
- **Title:** Development Toolchain Selection
- **Status:** ACCEPTED
- **Date:** 2026-08-07
- **Decision Type:** Architecture Decision
- **Category:** Development Infrastructure Decision
- **Decision Owner:** AIOS Project Owner
- **Approval Authority:** AIOS Governance Authority
- **Implementation Status:** Pending Implementation
- **Version:** 1.0.0


# 1. Context

AIOS has completed its foundational architecture decisions through ADR-0001 to ADR-0006.

The project has defined:
- Database architecture (ADR-0001, ADR-0006)
- Decision authority model (ADR-0002)
- Project structure alignment (ADR-0003)
- AI intelligence boundaries (ADR-0004)
- Event communication architecture (ADR-0005)
- Database migration and schema strategy (ADR-0006)

Before starting Phase 1 implementation, the project requires a controlled development environment with defined tools and engineering rules.

This ADR establishes the standard development toolchain to ensure:
- Consistent code quality.
- Reproducible development environments.
- Automated validation.
- Alignment with the Documentation Before Code principle defined by AIOS.


# 2. Problem Statement

The current AIOS documentation defines the technology stack but does not define:

- Python environment management.
- Dependency management process.
- Code formatting rules.
- Static analysis tools.
- Type checking strategy.
- Testing execution tools.
- Pre-commit validation workflow.

Without these decisions, different development environments may produce inconsistent results and reduce maintainability.


# 3. Decision Drivers

The decision is driven by:

1. Reproducible development environments.
2. Maintainable and readable codebase.
3. Early detection of defects.
4. Automated quality enforcement.
5. Compatibility with Python 3.10+.
6. Minimal operational complexity.
7. Alignment with AIOS governance principles.


# 4. Alternatives Considered

## Alternative 1: Minimal Tooling

Description:
Use only Python, pip, and manual code review.

Advantages:
- Simple setup.
- Minimal dependencies.

Disadvantages:
- No automated quality enforcement.
- Higher risk of inconsistent code.
- Difficult long-term maintenance.

Decision:
Rejected.


## Alternative 2: Traditional Python Toolchain

Description:
Use:
- venv
- pip
- requirements files
- black
- flake8
- mypy
- pytest

Advantages:
- Mature ecosystem.
- Widely adopted.
- Easy onboarding.

Disadvantages:
- Multiple independent tools.
- Additional configuration maintenance.

Decision:
Rejected in favor of a more integrated approach.


## Alternative 3: Modern Integrated Python Toolchain

Description:
Use:

- uv for environment and dependency management.
- Ruff for linting and formatting.
- Pyright for static type checking.
- Pytest for testing.
- Pre-commit for automated validation.

Advantages:
- Fast dependency management.
- Unified linting and formatting workflow.
- Strong developer feedback loop.
- Suitable for modern Python projects.

Disadvantages:
- Requires learning newer tooling.

Decision:
Selected.


# 5. Decision

AIOS will use the following development toolchain:

## 5.1 Project Configuration Location

Project metadata and development tool settings (uv, Ruff, Pyright, Pytest, and pre-commit) shall be stored in a single `pyproject.toml` file at the project root.

## 5.2 Python Environment

Python version:

- Python 3.10 or newer.

Environment management:

- uv virtual environments.

The project will maintain reproducible environments through locked dependencies.


## 5.3 Package Management

Dependency management:

- uv.

Rules:

- Dependencies must be declared in project configuration.
- Direct unmanaged package installation is prohibited for project dependencies.


## 5.4 Code Formatting

Formatter:

- Ruff Formatter.

Rules:

- Code formatting must be automated.
- Formatting changes must be applied before commit.


## 5.5 Static Analysis and Linting

Linting:

- Ruff.

Rules:

- Linting checks are required before merging changes.
- Violations must be resolved or explicitly documented.


## 5.6 Type Checking

Type checker:

- Pyright.

Rules:

- New production code should include type annotations.
- Type errors must not be ignored without justification.


## 5.7 Testing

Testing framework:

- Pytest.

Testing requirements:

- Tests must be executable locally.
- Test structure follows AIOS testing documentation.


## 5.8 Pre-Commit Validation

Git commits are mandatory validation points. Each commit must execute:

- Formatting checks.
- Lint checks.
- Type checks.
- Basic validation before commits.

Pre-commit hooks will enforce these checks, and failing checks must be resolved before the commit is accepted.


## 5.9 Continuous Integration Baseline

Future CI pipelines shall execute the same validation steps used locally:

- Dependency validation.
- Formatting check.
- Linting.
- Type checking.
- Tests.


# 6. Consequences

## Positive Consequences

- Consistent development workflow.
- Reduced code quality issues.
- Reproducible environments.
- Faster defect detection.
- Better preparation for team scaling.


## Negative Consequences

- Initial setup complexity.
- Developers must learn selected tools.
- Additional configuration files required.


## Risks

- Tool replacement may require migration effort.
- Incorrect configuration may block development.


# 7. Related Documents

- AIOS-002 Constitution
- AIOS-1106 Technical Stack
- AIOS-902 Decision Policy
- AIOS-906 Documentation Standard
- ADR-0001 Database Selection
- ADR-0003 Structure Alignment
- ADR-0006 Database Migration and Initial Schema


# 8. Change Log

| Version | Change |
|---|---|
| 1.0.0 | Initial proposal for Development Toolchain selection |
| 1.0.1 | Added project configuration location (pyproject.toml) and mandatory pre-commit validation policy |
| 1.0.2 | ADR formally accepted after governance review. |


**ADR Status:** ACCEPTED
