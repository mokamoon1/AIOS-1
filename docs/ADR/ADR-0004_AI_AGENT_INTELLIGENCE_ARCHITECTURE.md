# ADR-0004: AI Agent Intelligence Architecture

## Document Information

**ADR ID:** ADR-0004
**Title:** AI Agent Intelligence Architecture
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

AIOS is designed as a modular, AI-driven investment operating system.

The system is composed of independent components, specialized AI agents, and deterministic engines connected through controlled communication channels.

The AIOS documentation defines multiple related concepts:

* AIOS-101 System Architecture describes an AI Intelligence Layer feeding a Decision Engine.
* AIOS-102 Agent Architecture defines specialized agents such as the CIO Agent, Market Agent, Risk Agent, Portfolio Agent, and News Intelligence Agent.
* AIOS-403 Agent Design defines specialized agents that produce recommendations.
* AIOS-405 Analysis Engine Design defines analysis engines that produce scores and structured results.
* AIOS-406 Decision Engine Design defines a deterministic engine responsible for validation, scoring, rules, confidence, and explanation.
* ADR-0002 Decision Authority establishes the two-layer decision authority model: Analysis Engines, Decision Engine, CIO Agent Review, and Final Recommendation.

The project must define how intelligence operates inside AIOS before implementation begins.

---

# 2. Problem Statement

The AIOS documentation does not explicitly define how the intelligence of the system is implemented.

The following questions remain unresolved:

* Do AI agents depend on a Large Language Model (LLM)?
* Are AI agents deterministic software components?
* Who owns the final decision authority inside the system?
* Where is the boundary between Engines and Agents?
* Is an LLM allowed to influence investment decisions?

This ambiguity blocks Phase 1 implementation because the agent framework, engine interfaces, and decision workflow cannot be designed consistently while these questions remain open.

---

# 3. Decision Drivers

The decision shall satisfy the following drivers:

* **Capital Protection First:** The primary objective is protecting capital through risk control and evidence-based decisions (AIOS-002).
* **No Blind Decisions:** No investment decision may rely on random signals, single indicators, or unverified information (AIOS-002).
* **Explainability:** Every important decision must be explainable, with recorded reasons, data used, methods, and risks (AIOS-002, AIOS-406).
* **Testability:** Core computation must produce reproducible, testable results (AIOS-405, AIOS-406).
* **Separation of Concerns:** Business rules, analysis, decision logic, and AI reasoning must remain separated (AIOS-101, ADR-0002).
* **Governance and Safety:** Shariah Gate, Risk Gate, and portfolio rules must never be bypassed (AIOS-002, AIOS-1108).
* **Controlled AI Contribution:** AI agents are controlled engineering contributors and must not exceed their authority (AIOS-1108, AIOS-002).

---

# 4. Alternatives Considered

## Alternative 1: Fully Deterministic System

### Advantages

* Fully reproducible and testable.
* Predictable behavior with no hallucination risk.
* Complete auditability of every calculation.
* Simple governance and certification.
* No dependence on external AI providers.

### Disadvantages

* Limited ability to generate natural, human-readable explanations.
* Rigid user interaction.
* Difficult to summarize large analysis contexts meaningfully.
* Reduced flexibility for natural language reporting and queries.

---

## Alternative 2: Fully Autonomous LLM Agents

### Advantages

* Flexible natural language interaction.
* Ability to interpret and summarize complex information.
* Adaptable to new contexts without explicit programming.

### Disadvantages

* Non-deterministic and difficult to reproduce.
* High hallucination risk for financial calculations.
* Not safely testable for investment decisions.
* Risk of bypassing rules, gates, and governance.
* Contradicts the Explainability Requirement and the No Blind Decisions principle.
* Violates the separation between business rules and AI reasoning.

---

## Alternative 3: Hybrid Architecture

### Advantages

* Deterministic core computation remains testable and auditable.
* LLM is limited to explanation, summarization, and natural language interaction.
* Governance gates remain mandatory and cannot be bypassed.
* Combines reliability with a usable natural language interface.
* Preserves architectural integrity and future controlled expansion.

### Disadvantages

* Additional architectural complexity.
* Requires strict interface boundaries between components.
* Requires LLM governance, monitoring, and output validation.
* Higher integration and operational cost.

---

# 5. Decision

AIOS adopts the **Hybrid Architecture** for its intelligence layer.

The system is split into two distinct categories: **Engines** and **Agents**.

Engines and Agents remain independent components communicating through controlled interfaces as required by AIOS-101 and AIOS-002.

---

## 5.1 Engines

Engines are deterministic computation components.

### Responsibilities

* Perform calculations.
* Perform analysis.
* Perform evaluation.
* Produce Scores.
* Produce testable data.

### Limits

* Engines do not interpret or explain results using natural language.
* Engines do not communicate directly with the user.

### Outputs

Engines produce structured results such as:

* Market Score.
* Fundamental Score.
* Technical Score.
* Risk Score.
* Portfolio Score.
* Decision Score.

Engine examples:

* Market Engine.
* Fundamental Engine.
* Technical Engine.
* Risk Engine.
* Portfolio Engine.
* Decision Engine.

---

## 5.2 Agents

Agents are coordination and interpretation components.

### Responsibilities

* Coordinate between components.
* Manage context.
* Interpret engine results.
* Communicate between components.
* Produce human-readable reports.

### Permission Limits

Agents cannot:

* Override system rules.
* Change engine results.
* Bypass the Shariah Gate.
* Bypass Risk Controls.
* Issue a final decision directly.

Agent examples:

* CIO Agent.
* Market Agent.
* Fundamental Agent.
* Technical Agent.
* Risk Agent.
* Portfolio Agent.
* Shariah Compliance Agent.
* News Intelligence Agent.

---

## 5.3 LLM Role

A Large Language Model (LLM) may be used for selected non-decision tasks.

### Allowed

* Explanation of results.
* Summarization of analysis content.
* Natural Language Interface for user interaction.

### Forbidden

The LLM must never be used for:

* Direct BUY/SELL determination.
* Financial calculations.
* Modifying rules.
* Bypassing the Risk Gate.
* Bypassing the Shariah Gate.
* Overriding the Decision Engine.

Any usage of LLM capabilities outside the approved scope defined in this ADR requires a new ADR approval before implementation.

---

## 5.4 Decision Authority

The official decision authority remains consistent with ADR-0002:

```text
Analysis Engines

        ↓

Decision Engine

        ↓

CIO Agent Review

        ↓

Final Recommendation
```

* The Decision Engine issues the computational decision.
* The CIO Agent provides the final explanation and recommendation to the user.
* No component may bypass Governance.

The CIO Agent final recommendation is derived from the Decision Engine output and verified governance controls. CIO Agent does not independently create investment decisions.

---

# 6. Consequences

## Positive Consequences

* Core computation remains deterministic, reproducible, and testable.
* Financial decisions remain separated from AI reasoning.
* Shariah and Risk gates remain mandatory and non-bypassable.
* The system produces explainable decisions.
* A safe natural language interface is enabled.
* AI autonomy risk is reduced.

---

## Negative Consequences

* Increased architectural complexity.
* More components and interfaces to define and maintain.
* Requires clear boundary enforcement between Engines, Agents, and LLM.
* Requires additional testing and integration effort.

---

## Risks

* Boundary erosion over time between engines, agents, and LLM responsibilities.
* LLM output quality and hallucination in explanations.
* Prompt injection through user-facing interfaces.
* Unauthorized use of the LLM beyond the allowed scope.
* LLM latency and operational cost.
* Dependence on external LLM providers.

These risks shall be managed through interface enforcement, output validation, monitoring, and governance review during development.

---

# 7. Related Documents

* AIOS-002_PROJECT_CONSTITUTION
* AIOS-101_SYSTEM_ARCHITECTURE
* AIOS-102_AGENT_ARCHITECTURE
* AIOS-401_SYSTEM_DESIGN
* AIOS-403_AGENT_DESIGN
* AIOS-405_ANALYSIS_ENGINE_DESIGN
* AIOS-406_DECISION_ENGINE_DESIGN
* AIOS-1108_AI_DEVELOPMENT_GUIDELINES
* ADR-0001_DATABASE_SELECTION
* ADR-0002_DECISION_AUTHORITY
* ADR-0003_STRUCTURE_ALIGNMENT
* AIOS-902_DECISION_POLICY

---

# 8. Change Log

**Version:** 1.0.0

**Change:** Replaced previous invalid draft/prompt content with formal ADR decision document.

---

**Version:** 1.0.1

**Change:** ADR formally accepted after governance review.

---

**ADR Status:** ACCEPTED
