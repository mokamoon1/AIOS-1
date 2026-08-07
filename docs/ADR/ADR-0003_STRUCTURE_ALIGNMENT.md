# ADR-0003: AIOS Documentation Structure Alignment

## Document Information

**ADR ID:** ADR-0003
**Title:** AIOS Documentation Structure Alignment
**Status:** Accepted
**Date:** 2026-08-07
**Decision Type:** Architecture Decision

---

# 1. Context

During the architecture review of AIOS documentation, a mismatch was identified between historical documentation references and the actual repository structure.

Some documents referenced an older structure:

```text
03_REQUIREMENTS
04_DESIGN
09_GOVERNANCE
110_APPENDIX
```

while the current approved repository structure uses:

```text
03_INVESTMENT
04_AGENTS
09_OPERATIONS
10_APPENDIX
```

Maintaining two different structures creates ambiguity for:

* Developers.
* AI agents.
* Documentation management.
* Future contributors.

A single authoritative structure is required.

---

# 2. Decision

The current repository structure is the official AIOS structure.

The approved structure is:

```text
AIOS/

├── AI_BRAIN/

│   ├── 00_PROJECT
│   ├── 01_ARCHITECTURE
│   ├── 02_DOMAIN
│   ├── 03_INVESTMENT
│   ├── 04_AGENTS
│   ├── 05_DATA
│   ├── 06_DEVELOPMENT
│   ├── 07_TESTING
│   ├── 08_DEPLOYMENT
│   ├── 09_OPERATIONS
│   └── 10_APPENDIX

├── docs/

├── src/

├── tests/

└── README.md
```

This structure becomes the source of truth for all future development.

---

# 3. Directory Responsibilities

## 00_PROJECT

Contains:

* Project identity.
* Vision.
* Constitution.
* Scope.
* Roadmap.

---

## 01_ARCHITECTURE

Contains:

* System architecture.
* Agent architecture.
* Core design.
* Security architecture.
* Deployment architecture.

---

## 02_DOMAIN

Contains:

* Investment domain.
* Shariah compliance domain.
* Market analysis.
* Fundamental analysis.
* Technical analysis.
* Portfolio management.
* Risk management.

---

## 03_INVESTMENT

Contains:

* Investment requirements.
* Functional requirements.
* System requirements.
* Data requirements.
* Analysis requirements.
* Portfolio requirements.
* Risk requirements.

---

## 04_AGENTS

Contains:

* Agent design.
* Agent framework.
* Data flow.
* Analysis engine design.
* Decision engine design.
* API design.

---

## 05_DATA

Contains:

* Data architecture.
* Data models.
* Data sources.
* Validation.
* Storage.

---

## 06_DEVELOPMENT

Contains:

* Coding standards.
* Development workflow.
* Project structure.
* Implementation rules.

---

## 07_TESTING

Contains:

* Testing strategy.
* Unit testing.
* Integration testing.
* System testing.
* Backtesting.

---

## 08_DEPLOYMENT

Contains:

* Deployment strategy.
* Environment configuration.
* Release management.
* Backup and recovery.
* Maintenance policy.

---

## 09_OPERATIONS

Contains:

* Governance model.
* Decision policies.
* Change management.
* Risk management.
* Compliance.
* Audit.
* Continuous improvement.

---

## 10_APPENDIX

Contains:

* Glossary.
* Acronyms.
* Naming conventions.
* Coding references.
* Technology stack.
* Reference index.
* AI development guidelines.

---

# 4. Migration Rules

Future updates shall follow:

1. New documents must use the current folder structure.
2. No new top-level AI_BRAIN folders may be created without approval.
3. Existing document IDs remain unchanged.
4. Historical references to previous structures shall be updated when documents are revised.
5. The repository structure has priority over outdated references.

---

# 5. Naming Rules

AIOS documentation shall continue using:

```text
AIOS-[NUMBER]_[DOCUMENT_NAME].md
```

Examples:

```text
AIOS-000_PROJECT_MANIFEST.md
AIOS-101_SYSTEM_ARCHITECTURE.md
AIOS-1108_AI_DEVELOPMENT_GUIDELINES.md
```

Document IDs shall never be reused.

---

# 6. Reasons for Decision

This decision provides:

* One source of truth.
* Clear navigation.
* Better AI agent understanding.
* Reduced documentation conflicts.
* Stable long-term maintenance.

---

# 7. Consequences

## Positive Consequences

* AI agents can reliably locate documents.
* Developers follow one architecture map.
* Documentation remains organized.
* Future expansion becomes controlled.

---

## Negative Consequences

* Some older references require updating.
* Documentation review is required when files are modified.

---

# 8. Related Documents

* AIOS-000_PROJECT_MANIFEST
* AIOS-001_PROJECT_VISION
* AIOS-1103_NAMING_CONVENTIONS
* AIOS-1105_FILE_AND_FOLDER_STANDARDS
* AIOS-1107_REFERENCE_INDEX
* AIOS-1108_AI_DEVELOPMENT_GUIDELINES

---

# 9. Final Decision

**Approved Decision:**

The existing AIOS repository structure is the official and authoritative structure.

All future development, documentation, and AI agent operations must follow this structure.

---

**ADR Status:** ACCEPTED
