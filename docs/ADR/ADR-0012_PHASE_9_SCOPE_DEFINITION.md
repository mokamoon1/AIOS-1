# ADR-0012: Phase 9 Scope Definition

## Document Information

**ADR ID:** ADR-0012
**Title:** Phase 9 Scope Definition
**Status:** ACCEPTED
**Date:** 2026-08-09
**Decision Type:** Architecture Decision
**Category:** Phase Definition

---

# 1. Context

## 1.1 Current State

AIOS has completed Phase 8 (Data Ingestion Pipeline) with the following verified status:

- **Phase 8 Status:** COMPLETE — Data Ingestion Pipeline operational
  - Provider infrastructure (ProviderManager, ProviderFactory, Mock Providers)
  - Adapter Layer (DataProviderAdapter protocols + 3 concrete adapters)
  - IngestionService (single-symbol + batch/historical ingestion)
  - DataPipeline (6 stages: ACQUIRE→VALIDATE→NORMALIZE→QA→STORAGE→SERVE)
  - DataValidator (4-level validation: Schema, Field, Business Rules, Quality)
  - DataService (read facade + ingestion delegation)
  - All Gates operational (Shariah, Risk, Decision)
  - Paper Trading Safety preserved (no live providers, no live trading)
  - Repository Boundaries maintained
  - 790 unit/integration tests PASS
  - Operational Validation: 14/14 PASS
  - Configuration: `default_exchange` configurable via TOML/env

## 1.2 Roadmap Gap

The approved **AIOS-005 Project Roadmap** defines phases only through **Phase 6 (Production Readiness)**:

| Phase | Name | Status per Roadmap |
|-------|------|-------------------|
| Phase 0 | Engineering Foundation | IN PROGRESS (per roadmap) |
| Phase 1 | Core Platform | — |
| Phase 2 | Data Infrastructure | — |
| Phase 3 | Investment Intelligence | — |
| Phase 4 | Portfolio Management | — |
| Phase 5 | Paper Trading | — |
| Phase 6 | Production Readiness | — |

**There is no Phase 9 defined in any approved document.** The current implementation (through Phase 8) has already exceeded the roadmap's defined phases (Phases 1-6).

## 1.3 Scope Completion Assessment

Per **AIOS-003 Project Scope (V1)**, the following V1 features are implemented:

| V1 Feature (AIOS-003) | Status |
|----------------------|--------|
| Shariah Compliance System | ✅ Complete |
| Market Data System | ✅ Complete |
| Technical Analysis Engine | ✅ Complete |
| Fundamental Analysis Engine | ✅ Complete |
| AI Agent System (7 agents) | ✅ Complete |
| Portfolio Management | ✅ Complete |
| Paper Trading Integration | ✅ Complete |

**Gaps remaining for V1 Scope completion:**
- News Intelligence Engine (scaffold only in Phase 3)
- Signal Engine scoring (scaffold only in Phase 3/ADR-0002)
- Decision Engine scoring weights (placeholder — returns WAIT)
- Portfolio target allocation rules (not documented per AIOS-206)

## 1.4 Problem Statement

The project has organically extended beyond the approved roadmap (Phases 7-8 completed without formal Phase definitions). There is now ambiguity about:

1. **Is V1 complete?** — Scope criteria (AIOS-003 Section 6) appear largely met
2. **Is Phase 9 needed?** — No approved Phase 9 exists; any further work requires explicit scope definition
3. **What belongs in Phase 9 vs. V2/V3?** — Roadmap places advanced features in V2/V3
4. **Business rules pending** — Decision scoring, portfolio allocation, news provider selection

**A formal Phase 9 Scope Definition ADR is required before any further development.**

---

# 2. Decision Drivers

The Phase 9 scope decision shall satisfy:

1. **Constitutional Compliance** — Must not violate AIOS-002 principles (Capital Protection, No Blind Decisions, Explainability, Shariah Compliance, Paper Trading First)
2. **ADR Consistency** — Must not conflict with ADR-0001 through ADR-0011
3. **Scope Discipline** — Per AIOS-003 Section 7: "Does it support the main vision? Does it belong to current version? Does it justify additional complexity?"
3. **Gate Preservation** — Shariah Gate, Risk Gate, Decision Gate must remain inviolable
4. **Paper Trading Safety** — No live trading, no live providers without separate ADR
4. **Decision Authority** — ADR-0002 must remain inviolate (Decision Engine computes, CIO coordinates)
5. **Boundary Integrity** — Repository/DataAccess boundaries must not be crossed
6. **Business Rule Separation** — No business rules (scoring weights, allocation rules) hardcoded
6. **Documentation First** — Per AIOS-002 Section 7.1: documentation before implementation
6. **Testing Requirement** — Per AIOS-002 Section 7.2: tests before deployment
7. **Scope Discipline** — Per AIOS-003 Section 7: if not in current version → future version
7. **Approval Required** — Per AIOS-002 Section 9: architecture changes require review/approval

---

# 3. Proposed Decision

## 3.1 Phase 9 Definition

**Phase 9** is defined as: **"V1 Completion & Intelligence Maturation"**

**Goal:** Complete all V1 Scope commitments (AIOS-003) and mature intelligence components to production-grade reliability, while maintaining constitutional and ADR compliance.

**Relationship to V1:** Phase 9 **is** the V1 completion phase. Upon successful completion, AIOS V1.0 criteria (AIOS-005 Section 14) are satisfied.

**Relationship to Phase 8:** Phase 9 builds **on top of** Phase 8 infrastructure (IngestionService, Adapters, DataPipeline, Gates). Phase 9 does not modify Phase 8 foundations.

**Relationship to Phase 6 (Production Readiness):** Phase 9 **includes** production hardening activities for V1 components. If hardening scope expands beyond V1 completion, it may warrant a separate Phase 10.

**Relationship to V2/V3:** Phase 9 does **not** include V2/V3 features (multi-market, multi-broker, cloud, multi-user, autonomous management). Those remain in future versions per AIOS-003 Section 5 and AIOS-005 Section 12.

---

## 3.2 Phase 9 Scope (IN SCOPE)

| # | Component | Description | Dependencies |
|---|-----------|-------------|--------------|
| **9.1** | **News Intelligence Engine** | Implement NewsAgent/NewsEngine per AIOS-003 Section 3.4 & AIOS-005 Phase 3. Collect, evaluate, and explain market-relevant news. Integrate with Signal Engine. | Phase 8 Ingestion (data), Signal Engine (consumer), News Data Provider (PENDING BUSINESS DECISION) |
| **9.2** | **Signal Engine Implementation** | Implement scoring, ranking, filtering, confidence calculation per AIOS-605 Section 10. Consumes TechnicalEngine output. Produces directional signals (BUY/SELL/HOLD/WAIT) with evidence. | Technical Engine (complete), News Engine (9.1), configurable scoring (PENDING BUSINESS DECISION) |
| **9.3** | **Decision Engine Scoring** | Implement configurable scoring weights per AIOS-406 Sections 6-7. Transform Signal+Risk+Analysis outputs into directional decisions (BUY/SELL/HOLD/WAIT/NO_TRADE). Replace WAIT placeholder. | Signal Engine (9.2), Risk Engine (complete), Analysis Engines (complete), **scoring rules (PENDING BUSINESS DECISION)** |
| **9.4** | **Portfolio Target Allocation** | Implement target allocation rules, rebalancing logic per AIOS-206 Sections 6, 9. Enable PortfolioAgent to produce `recommended_allocation` and `rebalance_suggestion`. | PortfolioService (complete), Risk Engine (complete), **allocation rules (PENDING BUSINESS DECISION)** |
| **9.5** | **Backtesting Framework** | Implement historical simulation per AIOS-707. Replay historical data through full pipeline (Ingestion→Engines→Gates→Decision→PaperBroker). Generate performance reports. | All Engines, PaperBroker, Historical Data (via IngestionService), configurable strategies |
| **9.6** | **Production Hardening (V1 Scope)** | Security review, performance benchmarks, monitoring/alerting expansion, operational runbooks — **limited to V1 components only**. | All V1 components |

---

## 3.3 Out of Scope (EXPLICITLY EXCLUDED)

| Item | Reason | Target |
|------|--------|--------|
| Live Trading / Live Broker integration | Violates Constitution Section 8.1 (Paper Trading First) | Separate ADR + Approval required |
| Live Data Providers | Violates Constitution Section 8.1; requires ADR-0001 compliance | Separate ADR + Approval required |
| Multi-market (non-US equities) | AIOS-003 Section 4 (Excluded Features); AIOS-005 V2 | Version 2 |
| Cryptocurrency / Forex / Futures / Options | AIOS-003 Section 4 | Version 2+ |
| HFT / Market Making / Scalping | AIOS-003 Section 4 | Version 2+ |
| Multi-user / SaaS / Cloud / Mobile / Public API | AIOS-003 Section 4 | Version 3 |
| Autonomous Money Management | AIOS-003 Section 4 | Version 3+ |
| Advanced Portfolio Optimization | AIOS-005 V2 | Version 2 |
| Multiple Shariah Providers | AIOS-005 V2 | Version 2 |
| Decision Authority Changes | Violates ADR-0002, Constitution Section 4.2 | Never (requires constitutional amendment) |
| Bypassing Shariah/Risk/Decision Gates | Violates Constitution Section 3.3, ADR-0002 | Never |
| Repository/DataAccess Boundary Violations | Violates ADR-0001, ADR-0006 | Never |

---

## 3.4 Pending Business Decisions (PENDING BUSINESS DECISION)

**The following MUST be decided by Project Owner BEFORE implementation:**

| Decision | Description | Impact | Status |
|----------|-------------|--------|--------|
| **Decision Scoring Weights** | How to weight Signal, Risk, Technical, Fundamental, Market in Decision Engine. Formula, thresholds, weight ranges. | Core to 9.3; without this Decision Engine cannot produce directional decisions | **APPROVED** — See Section 3.4.1 |
| **Portfolio Target Allocation Rules** | Target sector weights, max position sizes, rebalancing triggers, drift tolerance. | Core to 9.4; without this Portfolio Agent cannot produce allocations | **APPROVED** — See Section 3.4.2 |
| **News Data Provider Selection** | Which provider(s), API terms, cost, data schema, update frequency. | Core to 9.1; without this News Engine has no data source | **APPROVED** — Mock provider for Phase 9.1-9.3 |
| **News Sentiment Methodology** | How to evaluate sentiment (rule-based, ML, hybrid), confidence thresholds. | Affects 9.1 signal quality | **APPROVED** — Rule-based keywords (Phase 9.1) |
| **Signal Scoring Methodology** | How to combine technical indicators into directional signals. Thresholds for BUY/SELL/HOLD/WAIT. | Core to 9.2 | **APPROVED** — Technical 70% + News 30%, thresholds 0.65/0.35 (Phase 9.2) |
| **Backtesting Strategy Scope** | Which historical periods, symbols, strategies, performance metrics. | Affects 9.5 scope | PENDING |
| **Production Hardening Scope** | Whether hardening stays in Phase 9 or becomes Phase 10. | Affects Phase 9 completion criteria | PENDING |

### 3.4.1 Approved Decision Scoring Rules (Phase 9.3)

**Component Weights:**
- Signal = 0.60 (contains Technical + News from Phase 9.2, no double-counting)
- Fundamental = 0.20
- Market = 0.20
- Technical = 0.00 (included in Signal)
- Risk = 0.00 (Hard Constraint, not scoring component)
- Portfolio = 0.00 (deferred to Phase 9.4)

**Scoring Formula:**
```
Decision Score = (Signal × 0.60) + (Fundamental × 0.20) + (Market × 0.20)
```
All components normalized to [-1.0, +1.0]: +1.0 = bullish, 0.0 = neutral, -1.0 = bearish.

**Decision Thresholds:**
- Score ≥ +0.65 → BUY
- Score ≤ -0.65 → SELL
- Otherwise → HOLD
- WAIT reserved for insufficient/invalid/low-confidence evidence (not for score near zero)

**Hard Constraints (priority order, non-overridable):**
1. **Shariah Gate**: Status ≠ COMPLIANT → NO_TRADE (absolute priority)
2. **Data Gate**: Required data missing/invalid/stale/insufficient → WAIT
3. **Analysis Gate**: Required analysis missing → WAIT
4. **Risk Gate**: approval_status = blocked → NO_TRADE
5. **Confidence Gate**: Confidence < 0.60 → WAIT

**Confidence Methodology:**
```
Confidence = 0.50 × Evidence Completeness + 0.30 × Component Agreement + 0.20 × Data Quality
```
Range: [0.0, 1.0]. Cannot override Hard Constraints.

**Configuration:** All weights, thresholds, confidence thresholds configurable via TOML/env (ADR-0009).

### 3.4.2 Approved Portfolio Allocation Rules (Phase 9.4)

**Allocation Score Components (normalized to [0.0, 1.0]):**
- Decision Score: 50% (from DecisionEngine decision_score mapped from [-1, +1] to [0, 1])
- Signal Score: 25% (from SignalEngine score [0, 1], already bullish-bias)
- Risk Score: 25% (from RiskEngine risk_score [0, 1] or derived)

**Allocation Score Formula:**
```
Allocation Score = (Decision_Score × 0.50) + (Signal_Score × 0.25) + (Risk_Score × 0.25)
```
Weights normalized internally. Result in [0.0, 1.0].

**Hard Constraints (priority order, non-overridable):**
1. **Shariah Gate**: status != COMPLIANT → allocation = 0
2. **Risk Gate**: approval_status = blocked → allocation = 0
3. **Decision Gate**: decision = WAIT or NO_TRADE → allocation = 0
4. **Decision Gate**: decision = HOLD → no new allocation (allocation = 0 for new positions)
5. **Risk Limits**: allocation must not exceed RiskEngine max_position_percentage or max_sector_exposure

**Risk Adjustment:**
- Target weight scaled by confidence and risk_score
- Max position weight and max portfolio exposure configurable
- Allocation cannot exceed RiskEngine maximum_allowable_exposure

**Rebalancing:**
- Rebalance triggered when position drift ≥ rebalance_threshold (default 5%)
- Minimum trade size configurable (min_trade_size)

**Configuration:** All weights, limits, thresholds configurable via TOML/env (ADR-0009).

---

# 4. Phase 9 Implementation Plan (Sequential Steps)

## Step 1: News Intelligence Engine (9.1)
- **Prerequisite:** News Provider selected, API integrated via ProviderFactory pattern
- **Deliverables:** NewsEngine (wired to SignalEngine), NewsAdapter, tests
- **Gate Check:** Shariah Gate — news must not bypass compliance

## Step 2: Signal Engine Implementation (9.2)
- **Prerequisite:** 9.1 complete (for news signals), Technical Engine output available
- **Deliverables:** SignalEngine with scoring, ranking, filtering, confidence
- **Gate Check:** Risk Gate — signals must carry risk metadata

## Step 3: Decision Engine Scoring (9.3)
- **Prerequisite:** 9.2 complete, scoring weights decided
- **Deliverables:** DecisionEngine produces BUY/SELL/HOLD/WAIT/NO_TRADE with scores
- **Gate Check:** All 4 gates (Shariah, Data, Analysis, Risk) must pass before directional decision

## Step 4: Portfolio Target Allocation (9.4)
- **Prerequisite:** 9.3 complete, allocation rules decided
- **Deliverables:** PortfolioAgent produces allocations, rebalance suggestions
- **Gate Check:** Risk Gate — allocations must respect risk limits

## Step 5: Backtesting Framework (9.5)
- **Prerequisite:** 9.1–9.4 complete
- **Deliverables:** Historical replay engine, performance reports, CI integration
- **Gate Check:** All Gates enforced during replay

## Step 6: Production Hardening (9.6)
- **Prerequisite:** 9.1–9.5 complete
- **Deliverables:** Security audit, performance benchmarks (<100ms ingestion, <500ms decision), monitoring dashboards, runbooks
- **Gate Check:** Regression test suite (790 tests) + Operational Validation (14/14)

---

# 5. Dependencies Summary

```
Phase 8 (Complete)
    │
    ├── 9.1 News Intelligence Engine ──→ 9.2 Signal Engine
    │                                         │
    │                    9.3 Decision Scoring ◄───┤
    │                                         │
    └── 9.4 Portfolio Allocation ◄────────────┘
                                    │
                              9.5 Backtesting Framework
                                    │
                              9.6 Production Hardening
```

---

# 6. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Business decisions delayed | High | Blocks 9.1–9.4 | Early escalation; parallel infrastructure work |
| Scope creep into V2 features | Medium | Dilutes V1 focus | Strict OOS list; gate reviews |
| Decision Engine scoring complexity | Medium | Delays 9.3 | Start with simple weighted sum; iterate |
| News Provider API instability | Medium | Blocks 9.1 | Provider abstraction; fallback/mock |
| Backtesting performance on large datasets | Medium | Delays 9.5 | Incremental processing; sampling |
| Production hardening scope expansion | Medium | Delays Phase 9 close | Strict V1-only boundary; Phase 10 if needed |
| Regression in existing Gates | Low | Critical | Mandatory Operational Validation (14/14) per step |

---

# 7. Acceptance Criteria

**Phase 9 is COMPLETE only when ALL criteria are met:**

| Criterion | Verification |
|-----------|--------------|
| **All existing tests PASS** | `pytest tests/ -q` → 790+ PASS |
| **Operational Validation 14/14 PASS** | `python tools/operational_validation.py` |
| **No Regression** | Zero failing tests from Phase 8 baseline |
| **No Live Trading paths enabled** | Code audit: no live broker/provider imports in main path |
| **No Gate Bypass** | Code audit: all Engine/Agent paths call `require_compliant()`, Risk/Decision validation |
| **No Secrets in Code** | `detect-secrets` scan PASS; no API keys in TOML |
| **Configuration via TOML + env vars** | All new settings in `[section]` with `AIOS_` prefix |
| **Documentation + ADR before implementation** | ADR-0012 ACCEPTED; AI_BRAIN docs updated per component |
| **Tests before adoption** | Unit + Integration tests per component; ≥90% coverage |
| **Decision Engine produces directional decisions** | BUY/SELL/HOLD/WAIT/NO_TRADE with scores (no WAIT placeholder) |
| **Portfolio Agent produces allocations** | `recommended_allocation`, `rebalance_suggestion` non-null |
| **Signal Engine produces evidence-based signals** | BUY/SELL/HOLD/WAIT with supporting technical/news evidence |
| **News Engine operational** | Collects, evaluates, explains market news |
| **Backtesting operational** | Historical replay produces performance reports |
| **Operational Validation 14/14 PASS post-Phase 9** | Full end-to-end validation |

---

# 7. Constitutional & ADR Impact Assessment

| Constitution Section | Impact | Compliance |
|---------------------|--------|------------|
| 2.1 Capital Protection | Enhanced via matured Risk/Decision | ✅ |
| 2.2 No Blind Decisions | Explainability via scoring evidence | ✅ |
| 2.3 Explainability | All new components produce explanations | ✅ |
| 3.1–3.3 Shariah Compliance | Gates unchanged; News respects gate | ✅ |
| 4.1–4.3 Agent Rules | New agents follow independence/authority rules | ✅ |
| 5.1–5.3 Architecture | Modular, controlled interfaces, scalable | ✅ |
| 6.1–6.2 Data Rules | Quality, traceability maintained | ✅ |
| 7.1–7.3 Development | Doc-before-code, tests, version control | ✅ |
| 8.1–8.3 Trading Rules | Paper-only; risk assessment; no forced trades | ✅ |
| 9 Change Management | ADR-0012 follows review/approval | ✅ |
| 10 Final Authority | Project Owner approval gate | ✅ |

| ADR | Impact | Compliance |
|-----|--------|------------|
| ADR-0001 (DB) | New tables via migrations only | ✅ |
| ADR-0002 (Decision Authority) | Decision Engine enhanced, authority unchanged | ✅ |
| ADR-0003 (Structure) | New modules follow AI_BRAIN structure | ✅ |
| ADR-0004 (AI Agents) | New agents follow framework | ✅ |
| ADR-0005 (Event Bus) | New events via bus | ✅ |
| ADR-0006 (Migrations) | Schema changes via Alembic | ✅ |
| ADR-0009 (Config) | New settings via TOML/env | ✅ |
| ADR-0010 (Logging) | JSON logs, correlation IDs | ✅ |
| ADR-0011 (Testing) | Tests before implementation | ✅ |

---

# 8. Required Approvals (قرارات مطلوبة من Project Owner)

**Before Phase 9 can begin, the Project Owner must explicitly approve:**

| # | Decision | Required For | Status |
|---|----------|--------------|--------|
| **1** | **Adopt Phase 9** — Confirm Phase 9 is authorized | All work | **APPROVED** |
| **2** | **Approve Phase 9 Scope** — Confirm In-Scope / Out-of-Scope lists | All work | **APPROVED** |
| **3** | **Approve Decision Scoring Rules** — Weights, thresholds, formulas | Step 9.3 | **APPROVED** |
| **4** | **Approve Portfolio Allocation Rules** — Targets, rebalancing logic | Step 9.4 | **APPROVED** |
| **5** | **Approve News Provider Strategy** — Provider(s), terms, schema | Step 9.1 | **APPROVED** (Mock) |
| **6** | **Decide Production Hardening Scope** — Within Phase 9 or separate Phase 10? | Step 9.6 | PENDING |

**Without explicit approval on ALL six items, Phase 9 remains BLOCKED.**

---

# 9. Recommendation

## Current State
- Phase 8 Complete (790 tests PASS, 14/14 Operational Validation)
- V1 Scope largely complete (gaps: News, Signal scoring, Decision scoring, Portfolio allocation)
- No approved Phase 9 in roadmap

## Recommendation

> **ADR-0012 Status: ACCEPTED**
>
> **Phase 9 Status: AUTHORIZED**
>
> **Phase 9 Implementation Authorized per Sequential Plan.**
>
> **Next Step:** Begin Phase 9.1 (News Intelligence Engine) implementation per the approved sequential plan in Section 4.

---

# 10. Document Status

**ADR ID:** ADR-0012
**Title:** Phase 9 Scope Definition
**Version:** 1.0.0
**Status:** **ACCEPTED**
**Date:** 2026-08-09
**Author:** AIOS Architecture Audit
**Approved By:** Project Owner
**Approval Date:** 2026-08-09
**Review Required:** Governance Authority

---

**This ADR has been ACCEPTED by Governance Authority per AIOS-002 Section 9 and ADR process. Phase 9 is now authorized for implementation per the approved scope and sequential plan.**