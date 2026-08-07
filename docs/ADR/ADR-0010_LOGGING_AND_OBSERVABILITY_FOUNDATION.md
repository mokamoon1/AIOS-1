# ADR-0010: Logging and Observability Foundation

## Document Information

- **ADR ID:** ADR-0010
- **Title:** Logging and Observability Foundation
- **Status:** ACCEPTED
- **Date:** 2026-08-07
- **Decision Type:** Architecture Decision
- **Category:** Application Foundation Decision
- **Decision Owner:** AIOS Project Owner
- **Approval Authority:** AIOS Governance Authority
- **Implementation Status:** Pending Implementation
- **Version:** 1.0.0


# 1. Context

AIOS has completed its foundational architecture decisions through ADR-0001 to ADR-0009.

The project has defined:

- Database architecture (ADR-0001, ADR-0006)
- Decision authority model (ADR-0002)
- Project structure alignment (ADR-0003)
- AI intelligence boundaries (ADR-0004)
- Event communication architecture (ADR-0005)
- Database migration strategy (ADR-0006)
- Development toolchain (ADR-0007)
- Application foundation for configuration and logging (ADR-0008)
- Configuration and environment management (ADR-0009)

ADR-0008 established the Python standard logging framework with structured logging support, defined logging levels, per-environment logging behavior, log storage destinations, and audit logging separation.

ADR-0005 established the Event Bus as the only communication path between components, with events persisted before dispatch and carrying a unique Event ID.

AIOS-104 defines the Logging System requirements, and AIOS-1104 defines logging standards and protected data rules.

Before starting Phase 1 coding, AIOS requires a concrete Logging and Observability Foundation that resolves the operational details left open by ADR-0008.


# 2. Problem Statement

ADR-0008 defines the logging framework and general requirements, but does not specify:

- The official logging library selection with rejected alternatives.
- The exact log format, including structured format for production.
- How audit logging integrates with the Event Bus defined by ADR-0005.
- How log entries are correlated across requests, events, and traces.
- Where logs are stored and the retention policy.
- The concrete security rules for preventing secrets in logs.

Without these decisions, components may produce inconsistent log formats, fail to support auditing and debugging, and risk exposing sensitive information.


# 3. Decision Drivers

The decision is driven by:

1. Consistency with ADR-0005, ADR-0008, and ADR-0009.
2. Structured and machine-readable production logs.
3. Auditability of decisions and security events.
4. Correlation across requests, events, and traces.
5. Secure handling of sensitive information.
6. Minimal operational complexity.
7. Alignment with AIOS governance and coding standards.


# 4. Alternatives Considered

## Alternative 1: Standard Library Logging Only

Description:

Use the Python standard logging library without any third-party logging dependency.

Advantages:

- Zero additional dependencies.
- Stable and mature.
- Consistent with ADR-0008.

Disadvantages:

- Manual JSON formatting.
- Limited structured logging helpers.
- More boilerplate for correlation fields.

Decision:

Selected as the base, with structured helpers.

## Alternative 2: Third-Party Logging Library (structlog)

Description:

Use structlog as the logging layer on top of the standard library.

Advantages:

- Rich structured logging support.
- Easier JSON rendering.
- Good developer ergonomics.

Disadvantages:

- Adds an external dependency beyond ADR-0008.
- Requires team adoption of a new API.
- Added learning curve for Phase 1.

Decision:

Rejected for Phase 1. May be reconsidered in a future ADR.

## Alternative 3: Custom Logging Framework

Description:

Build an in-house logging framework.

Advantages:

- Fully tailored behavior.

Disadvantages:

- High maintenance cost.
- Duplicates existing ecosystem functionality.
- Introduces risk and complexity.

Decision:

Rejected.

## Alternative 4: Plain Text Logs in All Environments

Description:

Use human-readable plain text logs in production.

Advantages:

- Simple to read directly.

Disadvantages:

- Poor machine parsing.
- Weak monitoring integration.
- Contradicts the structured logging direction of ADR-0008.

Decision:

Rejected.

## Alternative 5: JSON Structured Logs in All Environments

Description:

Use JSON logs in development and testing as well as production.

Advantages:

- Single format everywhere.

Disadvantages:

- Poor developer readability during active development.
- Contradicts the per-environment behavior in ADR-0008.

Decision:

Rejected. Development and Testing use readable format; Production uses JSON.


# 5. Decision

## 5.1 Logging Framework

AIOS uses the Python standard logging library as the official logging framework, consistent with ADR-0008.

A thin internal helper module provides structured field enrichment and consistent formatter configuration. No third-party logging library is used in Phase 1.

## 5.2 Log Format

All logs are structured logs containing structured fields.

Production:

- Logs use JSON format, machine-readable for monitoring and auditing.

Development and Testing:

- Logs use a human-readable formatted output for developer ergonomics.

Paper Trading:

- Logs follow the Production JSON format to validate production behavior.

The formatter is selected through the environment configuration defined in ADR-0009.

## 5.3 Log Levels

AIOS supports the following levels, consistent with ADR-0008 and AIOS-1104:

- DEBUG
- INFO
- WARNING
- ERROR
- CRITICAL

## 5.4 Environment Behavior

Development:

- DEBUG enabled.
- Human-readable format.

Testing:

- Configurable verbosity.
- Human-readable format with structured fields.

Paper Trading:

- INFO and above.
- JSON format.

Production:

- INFO/WARNING/ERROR according to operational requirements.
- JSON format.

## 5.5 Audit Logging

Audit logging records security and governance events, consistent with ADR-0008.

Audit events are emitted through the Event Bus defined by ADR-0005 as event records with a unique Event ID.

Sensitive events that must be logged:

- Decisions.
- Security checks.
- Permission violations.
- Risk events.

Audit logs remain separate from normal application debugging logs.

## 5.6 Correlation

Log entries include correlation identifiers to link related records:

- Request ID for incoming requests.
- Event ID for Event Bus events, matching ADR-0005.
- Trace ID for cross-component operations.

Correlation identifiers propagate across components through the Event Bus messages.

## 5.7 Storage and Retention

Log storage follows ADR-0008:

- Development and Testing: console output.
- Paper Trading and Production: rotating log files, with future monitoring integration.

Retention policy:

- Logs are retained per environment according to operational requirements.
- Audit logs are retained longer than debugging logs to satisfy audit and compliance requirements.

Storage configuration is defined through the configuration system established in ADR-0009.

## 5.8 Security

Logs must never contain:

- Secrets.
- API keys.
- Tokens.
- Passwords.
- Credentials.
- Private authentication data.

Sensitive fields are masked or excluded before logging.

Logging configuration and rotation must respect security rules defined by AIOS security documentation.


# 6. Consequences

## Positive Consequences

- Consistent, machine-readable production logs.
- Strong audit trail for decisions and security events.
- End-to-end correlation across requests, events, and traces.
- Secure handling of sensitive information.
- Consistency with ADR-0005, ADR-0008, and ADR-0009.

## Negative Consequences

- JSON format reduces direct human readability in production.
- Correlation propagation requires disciplined use of Event Bus metadata.
- Structured helper module requires maintenance.

## Risks

- Sensitive data may leak into logs if masking is incomplete.
- Inconsistent correlation may reduce traceability.
- Future observability needs may require a third-party library.


# 7. Related Documents

- AIOS-002 Constitution
- AIOS-104 Core Engine Design
- AIOS-802 Environment Configuration
- AIOS-902 Decision Policy
- AIOS-906 Documentation Standard
- AIOS-1104 Coding Standards
- AIOS-1106 Technical Stack
- ADR-0005 Event Bus Architecture
- ADR-0008 Application Foundation
- ADR-0009 Configuration and Environment Management


# 8. Change Log

| Version | Change |
|---|---|
| 1.0.0 | Initial proposal for Logging and Observability Foundation |
| 1.0.1 | ADR formally accepted after governance review. |


**ADR Status:** ACCEPTED
