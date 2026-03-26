# Agent Contracts

**YAML spec + validation SDK for production agent reliability.**

Cost control, tool-use security, and audit trails in under 30 minutes of integration. Works with any framework. Enforces at the runtime layer, not via prompts.

```
pip install aicontracts
```

## The Problem

Production agents fail at 41-87% rates. 97% of enterprises with agents in production haven't figured out how to scale them. The four pain points:

| Problem | Without Contracts | With Contracts |
|---------|------------------|----------------|
| **Cost runaway** | No ceiling on token spend | Budget circuit breaker per invocation |
| **Unauthorized tool use** | Ambient authority, prompt-bypassable | Default-deny allowlist at SDK layer |
| **No audit trail** | No record of authorized vs. actual | OTel-compatible violation events |
| **Silent regressions** | Prompt changes break things invisibly | Versioned contracts with SLO monitoring |

## 5-Minute Quick Start

### 1. Write a Contract (or generate one)

```yaml
# AGENT_CONTRACT.yaml
agent_contract: "0.1.0"

identity:
  name: my-agent
  version: "1.0.0"

contract:
  postconditions:
    - name: produces_output
      check: "output is not None"
      enforcement: sync_block
      severity: critical

effects:
  authorized:
    tools: [search, database.read]
    network: ["https://api.example.com/*"]

resources:
  budgets:
    max_cost_usd: 0.50
    max_tokens: 10000
    max_tool_calls: 20
```

Or generate from observed behavior:

```bash
aicontracts init --from-trace traces.jsonl -o AGENT_CONTRACT.yaml
```

### 2. Enforce at Runtime

```python
from agent_contracts import load_contract, ContractEnforcer

contract = load_contract("AGENT_CONTRACT.yaml")

with ContractEnforcer(contract) as enforcer:
    # Each tool call is checked against the allowlist and budget
    enforcer.check_tool_call("search")        # OK - in allowlist
    enforcer.check_tool_call("delete_all")    # BLOCKED - not authorized

    enforcer.add_cost(0.05)                   # Tracked against max_cost_usd
    enforcer.add_tokens(500)                  # Tracked against max_tokens

    # Postconditions evaluated after execution
    enforcer.evaluate_postconditions(result)
```

### 3. Framework Integration (3 lines)

**LangChain:**
```python
from agent_contracts.adapters.langchain import ContractCallbackHandler
handler = ContractCallbackHandler.from_file("AGENT_CONTRACT.yaml")
agent.invoke({"input": query}, config={"callbacks": [handler]})
```

**CrewAI:**
```python
from agent_contracts.adapters.crewai import ContractGuard
guard = ContractGuard.from_file("AGENT_CONTRACT.yaml")
result = guard.execute(crew, inputs={"query": query})
```

**Pydantic AI:**
```python
from agent_contracts.adapters.pydantic_ai import ContractMiddleware
middleware = ContractMiddleware.from_file("AGENT_CONTRACT.yaml")
result = await middleware.run(agent, prompt)
```

## Three Tiers

Start simple, add guarantees as production demands.

| Tier | Fields | Value |
|------|--------|-------|
| **0: Standalone** | identity + 1 postcondition (4 fields) | Self-documentation, local validation |
| **1: Enforceable** | + schemas, effects, budgets | Cost control, tool gating, I/O validation |
| **2: Composable** | + failure model, delegation, observability, SLOs | Multi-agent composition, audit trails, canary gates |

## CLI

```bash
# Validate a contract
aicontracts validate AGENT_CONTRACT.yaml

# Check composition compatibility
aicontracts check-compat producer.yaml consumer.yaml

# Generate from execution traces
aicontracts init --from-trace traces.jsonl

# Run eval suite against postconditions
aicontracts test AGENT_CONTRACT.yaml --eval-suite tests/
```

## Key Design Decisions

1. **Spec + SDK, not protocol or platform** — the OpenAPI model
2. **YAML primary** — JSON Schema validation, CEL-like inline expressions
3. **Graduated tiers** — Tier 0 is 4 fields, not 40
4. **Effects: authorized vs. declared** — intersection for delegation, union for audit
5. **Enforcement at SDK layer** — never in prompts (prompt injection can't bypass)
6. **MCP extension, not fork** — `x-agent-contract` on tool definitions

## Positioning

MCP governs how agents connect. Agent Skills govern what agents advertise.
A2A governs how agents find each other. **Agent Contracts govern what agents
must do, must not do, and what happens when they fail.**

## Project Structure

```
schemas/                    JSON Schema for AGENT_CONTRACT.yaml
spec/SPECIFICATION.md       Human-readable spec narrative
mcp/x-agent-contract.md    MCP extension proposal
src/agent_contracts/        Python SDK
  loader.py                 Contract loading + validation
  enforcer.py               Runtime enforcement middleware
  effects.py                Default-deny effect gating
  budgets.py                Budget tracking + circuit breaker
  postconditions.py         Postcondition evaluation
  violations.py             OTel-compatible violation events
  composition.py            Contract Differential checker
  cli.py                    CLI tool
  adapters/                 Framework adapters
examples/                   Reference contracts (Tier 0, 1, 2)
```

## License

Apache-2.0

## Author

Piyush Vyas
