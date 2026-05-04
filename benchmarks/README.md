# Performance Baselines

These baselines cover the hot paths that gate the `1.0.0` release:
effect authorization, postcondition evaluation, and bootstrapping a
contract from JSONL traces.

The executable regression tests live in `tests/test_performance_baselines.py`
and are part of the normal `pytest` suite. They enforce conservative
wall-clock budgets from `performance-baselines.json`; the JSON also records
the local baseline observed on May 4, 2026 using the macOS system
`python3` interpreter.

## Release Guardrails

- A release may tighten budgets only after measuring the same benchmark
  shapes locally and in CI.
- A release may loosen budgets only when the release plan explains the
  tradeoff and the change is not hiding an avoidable algorithmic regression.
- Behavior must remain identical when optimizing these paths: effect checks
  remain fail-closed, `eval:` postconditions do not pass without an explicit
  evaluator, and trace bootstrap output remains schema-compatible.
- If a budget fails intermittently, compare the recorded `baseline_ms` to the
  failed `max_ms` before changing code. The current budgets are intentionally
  several times higher than the local baseline to catch broad regressions
  without turning normal CI variance into a flaky release gate.
