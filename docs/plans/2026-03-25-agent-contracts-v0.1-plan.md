# Agent Contracts v0.1 — Implementation Plan

## Goal
Build the Agent Contracts v0.1 project: YAML spec + Python SDK + CLI + framework adapters + MCP extension proposal.

## Approach
Sequential implementation starting with the spec/schema foundation, then core SDK modules (bottom-up by dependency), CLI, adapters, and finally documentation/examples. Each task is independently committable and revertable.

## File Inventory

| File | Action | Task |
|------|--------|------|
| `pyproject.toml` | CREATE | T1 |
| `LICENSE` | CREATE | T1 |
| `src/agent_contracts/__init__.py` | CREATE | T1 |
| `src/agent_contracts/py.typed` | CREATE | T1 |
| `src/agent_contracts/_version.py` | CREATE | T1 |
| `schemas/agent-contract.schema.json` | CREATE | T2 |
| `src/agent_contracts/types.py` | CREATE | T3 |
| `src/agent_contracts/schema.py` | CREATE | T3 |
| `src/agent_contracts/loader.py` | CREATE | T4 |
| `src/agent_contracts/tier.py` | CREATE | T4 |
| `src/agent_contracts/effects.py` | CREATE | T5 |
| `src/agent_contracts/budgets.py` | CREATE | T5 |
| `src/agent_contracts/postconditions.py` | CREATE | T6 |
| `src/agent_contracts/violations.py` | CREATE | T6 |
| `src/agent_contracts/enforcer.py` | CREATE | T7 |
| `src/agent_contracts/composition.py` | CREATE | T8 |
| `src/agent_contracts/init_from_trace.py` | CREATE | T9 |
| `src/agent_contracts/cli.py` | CREATE | T9 |
| `src/agent_contracts/adapters/__init__.py` | CREATE | T10 |
| `src/agent_contracts/adapters/langchain.py` | CREATE | T10 |
| `src/agent_contracts/adapters/crewai.py` | CREATE | T10 |
| `src/agent_contracts/adapters/pydantic_ai.py` | CREATE | T10 |
| `examples/support_triage.yaml` | CREATE | T11 |
| `examples/simple_chatbot.yaml` | CREATE | T11 |
| `examples/cost_controlled.yaml` | CREATE | T11 |
| `AGENT_CONTRACT.yaml` | CREATE | T11 |
| `spec/SPECIFICATION.md` | CREATE | T12 |
| `mcp/x-agent-contract.md` | CREATE | T12 |
| `tests/conftest.py` | CREATE | T4 |
| `tests/test_loader.py` | CREATE | T4 |
| `tests/test_tier.py` | CREATE | T4 |
| `tests/test_effects.py` | CREATE | T5 |
| `tests/test_budgets.py` | CREATE | T5 |
| `tests/test_postconditions.py` | CREATE | T6 |
| `tests/test_violations.py` | CREATE | T6 |
| `tests/test_enforcer.py` | CREATE | T7 |
| `tests/test_composition.py` | CREATE | T8 |
| `tests/test_cli.py` | CREATE | T9 |
| `tests/test_init_from_trace.py` | CREATE | T9 |
| `tests/test_adapters/test_langchain.py` | CREATE | T10 |
| `tests/test_adapters/test_crewai.py` | CREATE | T10 |
| `tests/test_adapters/test_pydantic_ai.py` | CREATE | T10 |
| `README.md` | MODIFY | T13 |
| `.gitignore` | CREATE | T1 |
| `CLAUDE.md` | CREATE | T13 |

---

## Tasks

### T1: Project scaffolding and package configuration
- **What:** Create pyproject.toml (hatch build), LICENSE (Apache-2.0), .gitignore, package __init__.py, py.typed marker, _version.py
- **Files:** pyproject.toml, LICENSE, .gitignore, src/agent_contracts/__init__.py, src/agent_contracts/py.typed, src/agent_contracts/_version.py
- **LOC estimate:** ~120
- **Verify:** `cd /Users/piyush/GitHub/agent-contracts && python -m pip install -e ".[dev]" && python -c "import agent_contracts; print(agent_contracts.__version__)"`
- **Commit:** `build(project): scaffold package with pyproject.toml and Apache-2.0 license`
- **Rollback:** `git revert <SHA>`

### T2: JSON Schema for AGENT_CONTRACT.yaml (all 3 tiers)
- **What:** Create the formal JSON Schema that defines the AGENT_CONTRACT.yaml format. Covers Tier 0 (identity + postconditions), Tier 1 (+ schemas, effects.authorized, budgets), Tier 2 (+ failure_model, effects.declared, delegation, observability, versioning, slo). Supports x- extensions and must-ignore unknown fields.
- **Files:** schemas/agent-contract.schema.json
- **LOC estimate:** ~280
- **Verify:** `python -c "import json; s=json.load(open('schemas/agent-contract.schema.json')); print(s['title'])"`
- **Commit:** `feat(spec): add JSON Schema for AGENT_CONTRACT.yaml covering all 3 tiers`
- **Rollback:** `git revert <SHA>`

### T3: Core data models and schema module
- **What:** Define frozen dataclasses for Contract, ContractIdentity, PostconditionDef, EffectsAuthorized, EffectsDeclared, ResourceBudgets, DelegationRules, ObservabilityConfig, VersioningConfig, SLOConfig, SLODef. Schema module loads and exposes the JSON Schema.
- **Files:** src/agent_contracts/types.py, src/agent_contracts/schema.py
- **LOC estimate:** ~250
- **Verify:** `python -c "from agent_contracts.types import Contract, ResourceBudgets; print('OK')"`
- **Commit:** `feat(core): add typed data models and schema module`
- **Rollback:** `git revert <SHA>`

### T4: Contract loader, tier assessor, and tests
- **What:** YAML loading with schema validation, tier assessment (classify as 0/1/2 based on fields present), recommendation engine for missing fields. Shared test fixtures. Tests for loader and tier.
- **Files:** src/agent_contracts/loader.py, src/agent_contracts/tier.py, tests/conftest.py, tests/test_loader.py, tests/test_tier.py
- **LOC estimate:** ~300
- **Verify:** `cd /Users/piyush/GitHub/agent-contracts && python -m pytest tests/test_loader.py tests/test_tier.py -v`
- **Commit:** `feat(core): add contract loader with schema validation and tier assessment`
- **Rollback:** `git revert <SHA>`

### T5: Effect authorization and budget enforcement with tests
- **What:** Default-deny effect gating with glob pattern matching. Budget tracker with thread-safe counters, circuit breaker on threshold. Tests for both.
- **Files:** src/agent_contracts/effects.py, src/agent_contracts/budgets.py, tests/test_effects.py, tests/test_budgets.py
- **LOC estimate:** ~280
- **Verify:** `python -m pytest tests/test_effects.py tests/test_budgets.py -v`
- **Commit:** `feat(core): add effect authorization (default-deny) and budget enforcement`
- **Rollback:** `git revert <SHA>`

### T6: Postcondition evaluation and violation events with tests
- **What:** Postcondition evaluator supporting sync_block/sync_warn/async_monitor enforcement timing. Safe expression evaluator for CEL-like checks (no eval()). Violation event model (OTel-compatible). Event emitters: stdout, callback, optional OTel SDK. Tests.
- **Files:** src/agent_contracts/postconditions.py, src/agent_contracts/violations.py, tests/test_postconditions.py, tests/test_violations.py
- **LOC estimate:** ~280
- **Verify:** `python -m pytest tests/test_postconditions.py tests/test_violations.py -v`
- **Commit:** `feat(core): add postcondition evaluation and OTel-compatible violation events`
- **Rollback:** `git revert <SHA>`

### T7: Runtime enforcer (middleware) with tests
- **What:** ContractEnforcer class that wires together effects, budgets, postconditions, and violations into a unified enforcement flow. Supports decorator, context manager, and explicit API. Pre-call input validation, per-tool-call interception, post-call output validation.
- **Files:** src/agent_contracts/enforcer.py, tests/test_enforcer.py
- **LOC estimate:** ~250
- **Verify:** `python -m pytest tests/test_enforcer.py -v`
- **Commit:** `feat(core): add runtime enforcer with decorator, context manager, and explicit API`
- **Rollback:** `git revert <SHA>`

### T8: Composition checker (Contract Differential) with tests
- **What:** Given two Tier 2 contracts, compute schema gaps, capability gaps, budget gaps, effect validation (declared ⊆ authorized). Returns structured compatibility report.
- **Files:** src/agent_contracts/composition.py, tests/test_composition.py
- **LOC estimate:** ~200
- **Verify:** `python -m pytest tests/test_composition.py -v`
- **Commit:** `feat(core): add composition checker with Contract Differential analysis`
- **Rollback:** `git revert <SHA>`

### T9: CLI tool and trace-based init with tests
- **What:** Click-based CLI with 4 commands: validate, check-compat, init (from-trace), test. Trace parser reads JSONL execution traces and generates contract skeleton. Tests.
- **Files:** src/agent_contracts/cli.py, src/agent_contracts/init_from_trace.py, tests/test_cli.py, tests/test_init_from_trace.py
- **LOC estimate:** ~300
- **Verify:** `cd /Users/piyush/GitHub/agent-contracts && python -m agent_contracts.cli validate examples/support_triage.yaml` (after T11)
- **Commit:** `feat(cli): add validate, check-compat, init, and test commands`
- **Rollback:** `git revert <SHA>`

### T10: Framework adapters (LangChain, CrewAI, Pydantic AI) with tests
- **What:** Thin adapter wrappers (<200 LOC each) that map framework-specific hooks to the SDK's enforcement API. Each adapter enables 3-line contract enforcement integration. Tests with mocked framework interfaces.
- **Files:** src/agent_contracts/adapters/__init__.py, src/agent_contracts/adapters/langchain.py, src/agent_contracts/adapters/crewai.py, src/agent_contracts/adapters/pydantic_ai.py, tests/test_adapters/test_langchain.py, tests/test_adapters/test_crewai.py, tests/test_adapters/test_pydantic_ai.py
- **LOC estimate:** ~300 (adapters) + ~200 (tests)
- **Verify:** `python -m pytest tests/test_adapters/ -v`
- **Commit:** `feat(adapters): add LangChain, CrewAI, and Pydantic AI framework adapters`
- **Rollback:** `git revert <SHA>`

### T11: Reference examples and root contract
- **What:** Create example AGENT_CONTRACT.yaml files: support_triage (Tier 2, full), simple_chatbot (Tier 0, minimal), cost_controlled (Tier 1, budget-focused). Root AGENT_CONTRACT.yaml as the canonical reference. All must pass schema validation.
- **Files:** AGENT_CONTRACT.yaml, examples/support_triage.yaml, examples/simple_chatbot.yaml, examples/cost_controlled.yaml
- **LOC estimate:** ~200
- **Verify:** `python -m agent_contracts.cli validate AGENT_CONTRACT.yaml && python -m agent_contracts.cli validate examples/support_triage.yaml`
- **Commit:** `docs(examples): add reference AGENT_CONTRACT.yaml files for all 3 tiers`
- **Rollback:** `git revert <SHA>`

### T12: Specification narrative and MCP extension proposal
- **What:** Human-readable spec document explaining each field, the tier system, breaking change rules, and CEL expression syntax. MCP extension proposal for x-agent-contract on tool definitions.
- **Files:** spec/SPECIFICATION.md, mcp/x-agent-contract.md
- **LOC estimate:** ~250
- **Verify:** Manual review — documents should be complete and accurate
- **Commit:** `docs(spec): add human-readable specification and MCP extension proposal`
- **Rollback:** `git revert <SHA>`

### T13: README, CLAUDE.md, and public API surface
- **What:** Getting-started README with 5-minute contract experience, quick examples, API reference. CLAUDE.md for repo conventions. Polish __init__.py public exports.
- **Files:** README.md, CLAUDE.md, src/agent_contracts/__init__.py
- **LOC estimate:** ~200
- **Verify:** `python -c "from agent_contracts import Contract, ContractEnforcer, load_contract, validate_contract; print('Public API OK')"`
- **Commit:** `docs(readme): add getting-started guide and CLAUDE.md conventions`
- **Rollback:** `git revert <SHA>`
