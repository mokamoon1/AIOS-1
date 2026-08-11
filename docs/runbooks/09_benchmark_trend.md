# Runbook 09 - Benchmark / Trend

Measured latency budgets for the core engine paths, enforced by the performance
test suite and recorded for trend analysis (AIOS-705 section 12).

## Budgets

| Path | Metric | Budget |
|------|--------|--------|
| Data ingestion | `ingestion_latency_p99_ms` | < 100 ms |
| Decision engine | `decision_latency_p99_ms` | < 500 ms |

## How it works

`tests/performance/test_phase9_6_benchmarks.py`:

- Ingestion: feeds 100 `Candle` models through `DataPipeline`; excludes a
  warm-up run; takes 3 measured runs and asserts the p95 is under the budget.
- Decision: runs the full `DecisionEngine.execute` lifecycle 5 times and asserts
  the p95 is under the budget.
- Artifact: writes `tests/reports/phase9_6_benchmarks.json` (per-run and p95
  latencies, thresholds, timestamp) for trend analysis.

## Procedure

1. Run the benchmarks (performance marker):

   ```bash
   python -m pytest tests/performance -q -m performance
   ```

2. Compare the JSON artifact against the previous run; a p95 trending toward the
   budget triggers a performance investigation.
3. Promote threshold changes deliberately: any change must be recorded next to
   the thresholds in the test file and the trend artifact re-generated.

## Verification

```bash
python -m pytest tests/performance/test_phase9_6_benchmarks.py -q
```

## Notes

- Benchmarks run in CI as a separate `performance` marker and do not gate the
  unit/integration suites.
- Latency samples also flow into the alerting rule inputs via
  `AlertManager.record_latency(component, ms)` (Runbook 03).
