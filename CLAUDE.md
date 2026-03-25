# Agent Contracts

## What This Is

YAML spec + Python SDK for production agent reliability. Enforces cost control, tool-use security, and audit trails at the runtime boundary.

## Structure

```
schemas/agent-contract.schema.json    JSON Schema (all 3 tiers)
spec/SPECIFICATION.md                 Human-readable spec narrative
mcp/x-agent-contract.md              MCP extension proposal
src/agent_contracts/
  __init__.py                         Public API surface
  types.py                            Frozen dataclasses (Contract, etc.)
  schema.py                           JSON Schema loading + validation
  loader.py                           YAML loading → Contract objects
  tier.py                             Tier assessment (0/1/2) + recommendations
  effects.py                          Default-deny effect gating (glob patterns)
  budgets.py                          Thread-safe budget tracker + circuit breaker
  postconditions.py                   Safe expression evaluator (no eval())
  violations.py                       OTel-compatible violation events
  enforcer.py                         Unified enforcement middleware
  composition.py                      Contract Differential checker
  cli.py                              CLI (validate, check-compat, init, test)
  init_from_trace.py                  Generate contracts from JSONL traces
  adapters/
    langchain.py                      LangChain CallbackHandler
    crewai.py                         CrewAI ContractGuard
    pydantic_ai.py                    Pydantic AI ContractMiddleware
examples/                             Reference contracts (Tier 0, 1, 2)
tests/                                pytest test suite
```

## Conventions

- **Python 3.9+** — uses `from __future__ import annotations` for modern syntax
- **Type-safe** — full type annotations, `frozen=True` dataclasses, `py.typed` marker
- **No eval()** — CEL-like expressions parsed by safe evaluator
- **Default-deny** — effects.authorized is an allowlist; unlisted = blocked
- **Thread-safe** — budget counters use `threading.Lock`
- **Minimal deps** — core requires only pyyaml, jsonschema, click
- **Framework adapters** — optional extras, <200 LOC each

## Testing

```bash
pip install -e ".[dev]"
pytest                    # Run all tests
pytest -v                 # Verbose
pytest --cov             # With coverage
```

## Key Commands

```bash
agent-contracts validate contract.yaml
agent-contracts check-compat a.yaml b.yaml
agent-contracts init --from-trace traces.jsonl
agent-contracts test contract.yaml --eval-suite evals/
```

## Version

- Current: 0.1.0
- License: Apache-2.0
- Author: Piyush Vyas
