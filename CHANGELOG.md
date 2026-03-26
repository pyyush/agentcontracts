# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-25

First release. YAML spec + Python SDK for production agent reliability.

### Added

- **YAML Spec Schema** — JSON Schema (Draft 2020-12) covering 3 graduated tiers:
  - Tier 0 (Standalone): identity + postconditions (4 fields to start)
  - Tier 1 (Enforceable): + input/output schemas, effects authorization, budgets
  - Tier 2 (Composable): + failure model, delegation, observability, SLOs
- **Contract Loading** — YAML parsing, schema validation, tier assessment, upgrade recommendations
- **Effect Authorization** — Default-deny tool gating with glob pattern matching. Effects split: `authorized` (intersection during delegation) vs `declared` (union for audit)
- **Budget Enforcement** — Thread-safe circuit breaker for cost, tokens, tool calls, and elapsed time. Raises `BudgetExceededError` when thresholds are hit
- **Postcondition Evaluator** — Safe CEL-like expression evaluator (no `eval()`). Supports `is None`, comparisons, membership tests, `len()`. Three enforcement timings: `sync_block`, `sync_warn`, `async_monitor`
- **Violation Events** — OTel-compatible structured events with contract_id, violated_clause, evidence, severity, and trace context. Emits to stdout, OpenTelemetry SDK, or callback
- **Runtime Enforcer** — Unified middleware wiring effects, budgets, postconditions, and violations. Works as decorator (`@enforce_contract`), context manager, or explicit API
- **Composition Checker** — Contract Differential analysis: schema gaps, capability gaps, budget gaps, effect violations between producer/consumer contracts
- **CLI** — Four commands:
  - `agent-contracts validate` — schema validation + tier + recommendations
  - `agent-contracts check-compat` — composition compatibility check
  - `agent-contracts init --from-trace` — generate contract skeleton from JSONL traces
  - `agent-contracts test --eval-suite` — run eval suite against postconditions
- **Framework Adapters** — LangChain (`ContractCallbackHandler`), CrewAI (`ContractGuard`), Pydantic AI (`ContractMiddleware`). Each under 200 lines, 3-line integration
- **MCP Extension Proposal** — `x-agent-contract` for tool-level preconditions, effect declarations, and trust metadata
- **Specification** — Human-readable spec narrative (`SPECIFICATION.md`)
- **Examples** — Reference contracts for all 3 tiers

[0.1.0]: https://github.com/pyyush/agent-contracts/releases/tag/v0.1.0
