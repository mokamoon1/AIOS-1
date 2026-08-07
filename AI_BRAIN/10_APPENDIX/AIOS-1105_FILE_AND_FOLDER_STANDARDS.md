# AIOS-1105_FILE_AND_FOLDER_STANDARDS

## Document Information

**Document ID:** AIOS-1105
**Title:** File and Folder Standards
**Version:** 1.0.0
**Status:** APPROVED
**Category:** Appendix

---

# 1. Purpose

This document defines the official File and Folder Standards for AIOS.

The objective is to establish a consistent project structure that ensures maintainability, discoverability, scalability, and clear separation of responsibilities across all AIOS assets.

All developers, contributors, and AI agents shall follow this standard when creating or modifying files and directories.

---

# 2. Objectives

The File and Folder Standards shall:

* Maintain organized project structure.
* Prevent uncontrolled file growth.
* Improve navigation.
* Support automation.
* Simplify maintenance.
* Preserve architectural clarity.

---

# 3. Root Project Structure

The official AIOS root directory:

```text id="c8h5mv"
AI_BRAIN/
```

The root shall contain only approved top-level directories.

---

# 4. Official Top-Level Structure

```text id="r2x7nv"
AI_BRAIN/

├── 00_PROJECT

├── 01_ARCHITECTURE

├── 02_DOMAIN

├── 03_REQUIREMENTS

├── 04_DESIGN

├── 05_DATA

├── 06_DEVELOPMENT

├── 07_TESTING

├── 08_DEPLOYMENT

├── 09_GOVERNANCE

└── 110_APPENDIX
```

New top-level directories require governance approval.

---

# 5. Folder Naming Rules

Folders shall:

* Use uppercase naming.
* Use underscores between words.
* Avoid spaces.
* Use descriptive names.
* Follow approved numbering when part of the main structure.

Correct:

```text id="f8q2px"
06_DEVELOPMENT

MARKET_DATA

TRADING_ENGINE
```

Incorrect:

```text id="q7v9mw"
development files

MyFolder

temp
```

---

# 6. Documentation Structure

Documentation files shall remain inside their appropriate domain folder.

Example:

```text id="w3j8pq"
09_GOVERNANCE/

├── AIOS-901_GOVERNANCE_MODEL.md

├── AIOS-902_DECISION_POLICY.md

└── AIOS-908_CONTINUOUS_IMPROVEMENT.md
```

Documentation shall never be scattered randomly.

---

# 7. Development Structure

The development directory shall follow:

```text id="k5m3zx"
06_DEVELOPMENT/

├── core/

├── agents/

├── engines/

├── strategies/

├── brokers/

├── providers/

├── database/

├── services/

├── api/

├── utils/

└── config/
```

Each folder shall have a defined responsibility.

---

# 8. Data Structure

The data directory shall follow:

```text id="n9v4ks"
05_DATA/

├── raw/

├── processed/

├── historical/

├── market/

├── shariah/

├── models/

└── exports/
```

Data shall be separated according to lifecycle stage.

---

# 9. Testing Structure

The testing directory shall follow:

```text id="b6t9qy"
07_TESTING/

├── unit/

├── integration/

├── performance/

├── security/

├── regression/

└── reports/
```

Tests shall remain separated from production code.

---

# 10. Configuration Files

Configuration files shall be stored only in approved locations.

Examples:

```text id="z4q7mv"
config/

.env.example

settings.yaml

database.yaml
```

Secrets shall never be stored inside the repository.

---

# 11. Temporary Files

Temporary files shall:

* Not exist in production directories.
* Be excluded from version control.
* Use designated temporary locations.

Examples:

```text id="m2k8vx"
temp/

cache/

logs/
```

---

# 12. Generated Files

Generated files shall be separated from source files.

Examples:

```text id="x6p9qa"
build/

dist/

generated/

reports/
```

Generated assets shall not replace original sources.

---

# 13. Version Control Rules

Git repositories shall exclude:

* Virtual environments.
* Secret files.
* Cache files.
* Temporary files.
* Generated binaries.

Example:

```text id="h7m2kp"
venv/

.env

__pycache__/

*.log
```

---

# 14. File Creation Rules

Before creating a new file:

Verify:

* Correct folder location.
* Existing similar files.
* Naming convention.
* Documentation requirement.
* Testing requirement.

Duplicate files are prohibited.

---

# 15. AI Agent File Management Rules

AI agents modifying AIOS shall:

* Read folder standards first.
* Create files only in approved locations.
* Avoid restructuring directories without approval.
* Update indexes after creating new documents.
* Preserve existing architecture.

---

# 16. Future Expansion

Future folder standards may include:

* Microservice structures.
* Cloud deployment layouts.
* Machine learning pipelines.
* Model repositories.
* Data lake organization.

The structure shall evolve without breaking existing references.

---

# 17. Success Criteria

The File and Folder Standards are considered successful when:

* Every asset has a clear location.
* Project navigation remains simple.
* File duplication is minimized.
* Automation can rely on predictable paths.
* Architecture remains understandable.

---

# 18. Document Status

**Document ID:** AIOS-1105_FILE_AND_FOLDER_STANDARDS

**Version:** 1.0.0

**Status:** APPROVED
