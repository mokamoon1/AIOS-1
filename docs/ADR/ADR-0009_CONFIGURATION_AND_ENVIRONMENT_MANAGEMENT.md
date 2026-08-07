# ADR-0009: Configuration and Environment Management

## Document Information

- **ADR ID:** ADR-0009
- **Title:** Configuration and Environment Management
- **Status:** ACCEPTED
- **Date:** 2026-08-07
- **Decision Type:** Architecture Decision
- **Category:** Application Foundation Decision
- **Decision Owner:** AIOS Project Owner
- **Approval Authority:** AIOS Governance Authority
- **Implementation Status:** Pending Implementation
- **Version:** 1.0.0


# 1. Context

AIOS has completed its foundational architecture decisions through ADR-0001 to ADR-0008.

The project has defined:

- Database architecture (ADR-0001, ADR-0006)
- Decision authority model (ADR-0002)
- Project structure alignment (ADR-0003)
- AI intelligence boundaries (ADR-0004)
- Event communication architecture (ADR-0005)
- Database migration strategy (ADR-0006)
- Development toolchain (ADR-0007)
- Application foundation for configuration and logging (ADR-0008)

ADR-0008 established pydantic-settings as the configuration framework, defined configuration sources and their priority, and specified the four operational environments: Development, Testing, Paper Trading, and Production.

ADR-0007 established pyproject.toml as the single location for project metadata and development tool settings.

AIOS-802 defines environment configuration requirements, and AIOS-107 defines the deployment architecture. Phase 1 implementation requires a concrete, unified configuration and environment management approach that resolves the operational details left open by ADR-0008.


# 2. Problem Statement

ADR-0008 defines the configuration framework and the source priority, but does not specify:

- The configuration file format.
- Where environment-specific configuration files are located.
- How the active environment is identified at runtime.
- How environment-specific values are loaded and merged.
- The exact separation of concerns between pyproject.toml and runtime configuration.

Without these decisions, modules may introduce inconsistent configuration file formats, environment detection, and value override behavior.


# 3. Decision Drivers

The decision is driven by:

1. Consistency with ADR-0007 and ADR-0008.
2. Secure handling of sensitive values.
3. Explicit and reliable environment identification.
4. Single source of truth for runtime configuration.
5. Minimal operational complexity.
6. Compatibility with Python 3.10+ and the selected toolchain.
7. Alignment with AIOS governance principles.


# 4. Alternatives Considered

## Alternative 1: JSON Configuration Files

Description:

Use JSON files for runtime configuration.

Advantages:

- Widely supported.
- Simple to parse.

Disadvantages:

- No comments.
- Verbose for layered environment overrides.
- Weaker readability for configuration diffs.

Decision:

Rejected.


## Alternative 2: YAML Configuration Files

Description:

Use YAML files for runtime configuration.

Advantages:

- Human readable.
- Supports comments.

Disadvantages:

- Requires an additional dependency.
- Less natural validation integration with pydantic-settings.
- Complex edge cases in parsing.

Decision:

Rejected.


## Alternative 3: TOML Configuration Files

Description:

Use TOML files for runtime configuration.

Advantages:

- Native Python support.
- Consistent with pyproject.toml defined by ADR-0007.
- Readable and compact.
- Strong pydantic-settings integration.

Disadvantages:

- Fewer external editing tools compared to JSON/YAML.

Decision:

Selected.


## Alternative 4: Environment Variables Only

Description:

Manage all configuration through environment variables without configuration files.

Advantages:

- Simple override behavior.
- No file management.

Disadvantages:

- Difficult to maintain many values.
- Weak default management.
- Poor developer experience.

Decision:

Rejected in favor of a layered approach.


## Alternative 5: Layered Sources

Description:

Use default safe values, environment-specific configuration files, and environment variables in a defined priority order.

Advantages:

- Clear override behavior.
- Safe defaults.
- Secure secret handling.
- Environment isolation.

Disadvantages:

- Slightly more complex startup logic.

Decision:

Selected.


# 5. Decision

## 5.1 Configuration Sources

AIOS configuration is loaded from three sources:

1. Default safe values defined by the application.
2. Environment-specific configuration files.
3. Environment variables.

This matches the sources defined in ADR-0008 Section 5.1.

## 5.2 Configuration Priority

The priority order is:

1. Environment variables (highest priority).
2. Environment-specific configuration files.
3. Default safe values (lowest priority).

Higher-priority sources override lower-priority sources for the same setting.

## 5.3 Configuration File Format

Runtime configuration files use TOML.

Rationale:

- Native Python support via tomllib on Python 3.11+, with the tomli backport required on Python 3.10.
- Consistent with pyproject.toml established by ADR-0007.
- Good pydantic-settings integration.

## 5.4 Environment Identification

The active environment is identified at runtime through a mandatory environment variable:

```text
AIOS_ENVIRONMENT
```

Valid values:

```text
development
testing
paper
production
```

AIOS refuses to start when:

- AIOS_ENVIRONMENT is missing.
- AIOS_ENVIRONMENT contains an unsupported value.

This provides the explicit runtime identification required by ADR-0008 Section 5.2.

## 5.5 Environment-Specific Configuration Files

Each environment may load its own configuration file in TOML format.

Environment-specific configuration files are stored in the `config/` directory as defined by AIOS-601.

File naming convention:

```text
config.<environment>.toml
```

Examples:

```text
config/config.development.toml
config/config.testing.toml
config/config.paper.toml
config/config.production.toml
```

Values defined in the active environment file override default safe values but remain below environment variables in priority.

## 5.6 Secret Management

Secrets are provided exclusively through environment variables.

Examples:

- API keys.
- Database credentials.
- Broker credentials.

Secrets must not be stored in:

- Source code.
- Configuration files.
- Documentation.
- Committed files of any type.

This matches ADR-0008 Section 5.3.

## 5.7 Separation Between Tool Settings and Runtime Configuration

- Project metadata and development tool settings (uv, Ruff, Pyright, Pytest, pre-commit) remain in pyproject.toml as defined by ADR-0007.
- Runtime application configuration uses environment-specific TOML files and environment variables.
- pyproject.toml must not contain runtime secrets or environment-specific runtime values.

## 5.8 Environment Separation

AIOS supports the following environments:

- Development.
- Testing.
- Paper Trading.
- Production.

Staging is not part of the Phase 1 operational environments and may be added in the future without changing the configuration system architecture, consistent with ADR-0008.

Each environment must have:

- Separate configuration values.
- Separate secrets.
- Explicit runtime identification through AIOS_ENVIRONMENT.


# 6. Consequences

## Positive Consequences

- Unified configuration behavior across all components.
- Clear and secure secret handling.
- Explicit environment isolation.
- Consistency with ADR-0007 and ADR-0008.
- Reproducible startup behavior.

## Negative Consequences

- Environment-specific configuration files require maintenance.
- AIOS_ENVIRONMENT must be set in every runtime.
- Additional validation rules at startup.

## Risks

- Incorrect environment identification may load the wrong configuration.
- Secrets may be misconfigured if environment variables are not properly managed.
- Future environments require file and validation updates.


# 7. Related Documents

- AIOS-002 Constitution
- AIOS-107 Deployment Architecture
- AIOS-603 Configuration Requirements
- AIOS-802 Environment Configuration
- AIOS-902 Decision Policy
- AIOS-906 Documentation Standard
- AIOS-1106 Technical Stack
- ADR-0007 Development Toolchain
- ADR-0008 Application Foundation


# 8. Change Log

| Version | Change |
|---|---|
| 1.0.0 | Initial proposal for Configuration and Environment Management |
| 1.0.1 | Clarified TOML runtime support, configuration directory location, and corrected AIOS-107 reference naming. |
| 1.0.2 | ADR formally accepted after governance review. |


**ADR Status:** ACCEPTED
