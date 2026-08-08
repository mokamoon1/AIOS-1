# AIOS-1107_REFERENCE_INDEX

## Document Information

**Document ID:** AIOS-1107
**Title:** Reference Index
**Version:** 1.0.0
**Status:** APPROVED
**Category:** Appendix

---

# 1. Purpose

This document defines the official reference index for AIOS documentation.

The purpose of this index is to provide a centralized map of all AIOS documents, their relationships, locations, and intended reading order.

This document acts as the navigation guide for developers, reviewers, maintainers, and AI agents working on AIOS.

---

# 2. Objectives

The Reference Index shall:

* Provide documentation navigation.
* Maintain document relationships.
* Reduce information discovery time.
* Support onboarding.
* Preserve project knowledge.

---

# 3. AIOS Documentation Architecture

The AIOS documentation system follows:

```text id="j5v8rx"
AIOS Constitution

        │

        ▼

Project Definition

        │

        ▼

Architecture

        │

        ▼

Domain Knowledge

        │

        ▼

Investment

        │

        ▼

Agents

        │

        ▼

Data

        │

        ▼

Development

        │

        ▼

Testing

        │

        ▼

Deployment

        │

        ▼

Operations

        │

        ▼

Appendix
```

---

# 4. Official Documentation Structure

## 00_PROJECT

Purpose:

Defines project identity, objectives, scope, and foundations.

Contains:

* Project Charter.
* Vision.
* Objectives.
* Scope.
* Roadmap.

---

## 01_ARCHITECTURE

Purpose:

Defines system structure and architectural decisions.

Contains:

* System architecture.
* Components.
* Data flow.
* Integration design.
* Architectural decisions.

---

## 02_DOMAIN

Purpose:

Defines AIOS business and trading domain knowledge.

Contains:

* Trading concepts.
* Market concepts.
* Shariah requirements.
* Financial terminology.

---

## 03_INVESTMENT

Purpose:

Defines system requirements.

Contains:

* Functional requirements.
* Non-functional requirements.
* User requirements.
* System constraints.

---

## 04_AGENTS

Purpose:

Defines detailed system design.

Contains:

* Module design.
* Database design.
* Interface design.
* Process design.

---

## 05_DATA

Purpose:

Defines data management.

Contains:

* Data architecture.
* Data sources.
* Data models.
* Data quality standards.

---

## 06_DEVELOPMENT

Purpose:

Defines implementation standards and development resources.

Contains:

* Source code.
* Development guidelines.
* Engineering procedures.

---

## 07_TESTING

Purpose:

Defines verification and validation.

Contains:

* Test plans.
* Test cases.
* Quality standards.
* Test reports.

---

## 08_DEPLOYMENT

Purpose:

Defines operational release procedures.

Contains:

* Deployment processes.
* Environment configuration.
* Release management.

---

## 09_OPERATIONS

Purpose:

Defines project control and oversight.

Contains:

* Governance model.
* Risk management.
* Compliance.
* Audit.
* Continuous improvement.

---

## 10_APPENDIX

Purpose:

Provides reference information.

Contains:

* Glossary.
* Acronyms.
* Standards.
* Technology references.
* AI guidelines.

---

# 5. Document Relationship Map

```text id="e8k3mv"
Investment

      ↓

Architecture

      ↓

Agents

      ↓

Development

      ↓

Testing

      ↓

Deployment

      ↓

Operations

      ↓

Continuous Improvement
```

All documents shall maintain consistency with this dependency flow.

---

# 6. Document Lookup Rules

When searching for information:

## Project Questions

Start with:

```text id="q4x8zn"
00_PROJECT
```

---

## Technical Questions

Start with:

```text id="z7m2kp"
01_ARCHITECTURE

04_AGENTS

06_DEVELOPMENT
```

---

## Data Questions

Start with:

```text id="v3r9mq"
05_DATA
```

---

## Operational Questions

Start with:

```text id="k8n4wp"
08_DEPLOYMENT

09_OPERATIONS
```

---

## Terminology Questions

Start with:

```text id="s6q2mv"
10_APPENDIX
```

---

# 7. AI Agent Navigation Rules

AI agents working on AIOS shall:

1. Read relevant documentation before modification.
2. Identify affected domains.
3. Review related architecture documents.
4. Check governance requirements.
5. Update references after changes.

No AI agent shall modify isolated files without understanding related documentation.

---

# 8. Documentation Dependency Rules

Documents shall reference:

* Parent documents.
* Related documents.
* Required standards.

Circular undocumented dependencies are prohibited.

---

# 9. Reference Maintenance

The Reference Index shall be updated when:

* New documents are created.
* Documents are renamed.
* Structure changes.
* New domains are introduced.

---

# 10. Future Expansion

Future index capabilities may include:

* Automated documentation graph.
* AI-powered search.
* Dependency visualization.
* Knowledge graph integration.
* Documentation health monitoring.

---

# 11. Success Criteria

The Reference Index is considered successful when:

* Every document can be located quickly.
* Relationships are clear.
* New contributors understand project structure.
* AI agents can navigate the system reliably.

---

# 12. Change Log

| Version | Change |
|---|---|
| 1.0.0 | Initial release of Reference Index |
| 1.0.1 | Aligned documentation structure and relationship maps with ADR-0003 approved structure |
| 1.0.2 | Clarified Phase 1 core agent roster authority: within Phase 1, AIOS-604 (confirmed by AIOS-401 and AIOS-403) is the canonical source for the seven-agent roster (CIO, Shariah, Market, Technical, Fundamental, Risk, Portfolio). Broader agent examples in AIOS-101 and AIOS-102 (for example the News Intelligence Agent and the combined market/technical agent) are future expansion and do not change the Phase 1 core roster. |

---

# 13. Document Status

**Document ID:** AIOS-1107_REFERENCE_INDEX

**Version:** 1.0.0

**Status:** APPROVED
