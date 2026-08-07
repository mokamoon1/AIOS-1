# ADR-0002: Decision Authority Model

## Document Information

**ADR ID:** ADR-0002
**Title:** Decision Authority Model
**Status:** Accepted
**Date:** 2026-08-07
**Decision Type:** Architecture Decision

---

# 1. Context

AIOS documentation contained ambiguity regarding the final investment decision authority.

Two concepts appeared:

1. **CIO Agent**

   * Defined as the highest-level investment coordinator.
   * Responsible for collecting agent outputs and producing the final recommendation.

2. **Decision Engine**

   * Defined as the engine responsible for validating rules, scoring, confidence evaluation, and issuing investment recommendations.

The system requires a clear separation between computational decision logic and AI agent responsibility.

---

# 2. Decision

AIOS adopts a two-layer decision authority model:

```text
Analysis Engines

        ↓

Decision Engine

        ↓

CIO Agent

        ↓

Final Investment Recommendation
```

---

# 3. Responsibilities

## 3.1 Analysis Engines

Responsible for:

* Market analysis.
* Fundamental analysis.
* Technical analysis.
* Risk calculations.
* Portfolio analysis.

They provide:

* Data.
* Scores.
* Signals.
* Reports.

They cannot issue final decisions.

---

# 3.2 Decision Engine

The Decision Engine is responsible for:

* Collecting validated analysis outputs.
* Applying investment rules.
* Applying risk restrictions.
* Calculating decision confidence.
* Validating mandatory gates.
* Generating a structured decision proposal.

Decision Engine outputs:

* BUY
* SELL
* HOLD
* WAIT
* NO TRADE

The Decision Engine is the system's formal decision calculation layer.

---

# 3.3 CIO Agent

The CIO Agent is responsible for:

* Reviewing Decision Engine output.
* Coordinating specialist agents.
* Evaluating agreement and conflicts.
* Producing human-readable explanation.
* Presenting the final investment recommendation.

The CIO Agent does not bypass:

* Shariah rules.
* Risk controls.
* System policies.
* Decision validation.

---

# 4. Decision Flow

The official AIOS decision workflow:

```text
Security Candidate

        ↓

Shariah Verification Gate

        ↓

Market Analysis

        ↓

Fundamental Analysis

        ↓

Technical Analysis

        ↓

Risk Evaluation

        ↓

Portfolio Evaluation

        ↓

Decision Engine

        ↓

CIO Agent Review

        ↓

Final Recommendation

        ↓

Paper Trading Execution
```

---

# 5. Reasons for Decision

## 5.1 Separation of Responsibilities

The Decision Engine performs deterministic validation.

The CIO Agent performs intelligent coordination and explanation.

This prevents mixing business rules with AI reasoning.

---

## 5.2 Explainability

Every final recommendation must contain:

* Decision.
* Reason.
* Supporting evidence.
* Risk level.
* Confidence score.
* Timestamp.

---

## 5.3 Safety

No single AI agent can independently execute investment actions.

Mandatory controls remain enforced:

* Shariah Gate.
* Risk Gate.
* Portfolio Rules.
* Decision Validation.

---

# 6. Consequences

## Positive Consequences

* Clear system responsibility.
* Better explainability.
* Easier testing.
* Reduced AI autonomy risk.
* Improved governance.

---

## Negative Consequences

* Additional architectural complexity.
* More communication between components.
* Requires clear interfaces.

---

# 7. Implementation Rules

Developers and AI agents must:

* Keep Decision Engine independent from CIO Agent.
* Never allow CIO Agent to bypass validation.
* Keep analysis engines separate from decision authority.
* Record all decisions in the audit system.

---

# 8. Related Documents

* AIOS-102_AGENT_ARCHITECTURE
* AIOS-208_TRADING_DECISION_DOMAIN
* AIOS-403_AGENT_DESIGN
* AIOS-405_ANALYSIS_ENGINE_DESIGN
* AIOS-406_DECISION_ENGINE_DESIGN
* AIOS-1108_AI_DEVELOPMENT_GUIDELINES

---

# 9. Final Decision

**Approved Decision:**

The Decision Engine is responsible for formal decision computation.

The CIO Agent is responsible for coordination, explanation, and final presentation of the investment recommendation.

---

**ADR Status:** ACCEPTED
