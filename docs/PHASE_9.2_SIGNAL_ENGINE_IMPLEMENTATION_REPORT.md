# Phase 9.2 — Signal Engine Implementation Report

Status: Complete
Date: 2026-08-09
References: ADR-0009, ADR-0011, ADR-0012, AIOS-605 sections 10/13/15, AIOS-305 section 7, AIOS-208 section 10

## 1. Objective

Implement the Signal Engine (AIOS-605 section 10) as a real engine that consumes
Technical Engine outputs and News Intelligence in the live runtime and produces a
documented directional output (BUY / SELL / HOLD / WAIT) with a bullish-bias score,
confidence, evidence, and explanation. The previously broken Signal Engine / News
Engine wiring in the core startup sequence was fixed as part of this phase.

## 2. Approved Decisions

1. **Scoring (Project Owner approved):** The Signal bullish bias is a single value in
   [0.0, 1.0] combining technical (weight 0.70) and news (weight 0.30) components via
   `weighted_score()` (AIOS-305 section 7). Thresholds are configurable: score >= buy
   (0.65) -> BUY, <= sell (0.35) -> SELL, otherwise HOLD. WAIT is produced whenever
   required data is missing, news coverage is below `min_news_items`, or confidence is
   below `min_confidence` (AIOS-605 section 15, AIOS-208 section 10).
2. **Wiring fix (Project Owner approved):** Build a real `NewsEngine` from the connected
   `NewsDataProviderAdapter` and inject it into the registered `SignalEngine` after
   providers connect; pass `news_adapter`/`news_repository` into `IngestionService`.
   All tunables live in TOML/environment only (ADR-0009).

## 3. Implementation

| File | Change |
| --- | --- |
| `src/aios/analysis/models.py` | Added `SignalDirection` (buy/sell/hold/wait) and `SignalResult` (score, confidence, components, technical_score, news_score, news_items, evidence, explanation, reasons). |
| `src/aios/analysis/__init__.py` | Exported `SignalDirection`, `SignalResult`. |
| `src/aios/config/settings.py` | Added `SignalSettings` (weights, thresholds, `min_confidence`, `min_news_items`, `require_news`) under `AIOS_SIGNAL_` env prefix. |
| `src/aios/config/loader.py` | Wire `[signal]` TOML section + env overrides into `AppSettings.signal`. |
| `config/config.{development,testing,paper,production}.toml` | Added `[signal]` section with documented defaults. |
| `src/aios/engines/roster.py` | Implemented `SignalEngine._analyze` + helpers (`_technical_bullish_bias`, `_news_bullish_bias`, `_signal_confidence`, `_signal_result`); `SignalEngine` accepts injected `SignalSettings`. |
| `src/aios/core/engine.py` | Fixed wiring: real `NewsEngine` built from the connected news adapter and attached via `SignalEngine.attach_news_engine()`; `NewsRepository` passed to `IngestionService`. |
| `src/aios/data/ingestion.py` | Fixed `ingest_news` `progress_callback` NameError (parameter was referenced but never declared). |

### Signal behavior

- **Technical component:** mapped from structure direction/strength (AIOS-205 section 5):
  uptrend -> 0.5 + 0.5*strength, downtrend -> 0.5 - 0.5*strength, range -> 0.5.
- **News component:** per-item sentiment score [-1, 1] (AIOS-102 section 9) mapped to
  [0, 1] and relevance-weighted average across analyzed articles.
- **Confidence:** data completeness x component agreement (conflicting technical/news
  reduces confidence so weak or contradictory evidence never yields BUY/SELL).
- **WAIT gating:** missing required data, `news_items < min_news_items`, or
  `confidence < min_confidence` -> WAIT (no directional opinion from weak evidence).

## 4. Verification

- Full suite: `python -m pytest tests/ -q` -> **810 passed** (baseline 794 + 16 new tests:
  10 Signal Engine behavior tests, 6 `[signal]` configuration tests).
- Operational validation: `python tools/operational_validation.py` -> **14/14 passed, exit 0**;
  `logs/operational_validation.txt` written. Full analysis pipeline (including Signal Engine
  with attached News Engine) executed end-to-end without failure.

## 5. Compliance

- Engines consume data only through `DataAccess`; no direct database/repository access
  (AIOS-501 section 2, AIOS-605 section 13).
- No changes to the Decision Engine, portfolio allocation, Shariah, risk limits, or
  Decision Authority (ADR-0002). Decision Engine still yields the documented WAIT until
  decision scoring is configured.
- No live providers or trading introduced; Paper Trading uses mock providers only.
- No secrets added; configuration is TOML/env per ADR-0009.
- No commits/pushes made.

## 6. Next Steps

- Define Decision Engine directional scoring weights (AIOS-406 sections 6-7).
- Approve a live news data source to replace mock news (AIOS-303 section 14, AIOS-502 section 15).
