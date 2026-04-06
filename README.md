# Agent Contracts

[![CI](https://github.com/pyyush/agentcontracts/actions/workflows/ci.yml/badge.svg)](https://github.com/pyyush/agentcontracts/actions/workflows/ci.yml)

**Repo-local, fail-closed guardrails for autonomous coding/build agents.**

`agent-contracts` lets a repository declare what an agent may read, write, run, call, and spend — and then emit one durable verdict artifact showing whether the run passed, warned, blocked, or failed.

```bash
pip install aicontracts
```

## What it solves

Without a repo-local contract, coding agents usually run with ambient authority.
That creates five common failure modes:

- edits outside the intended file scope
- forbidden shell commands
- unauthorized tool or network calls
- silent budget overruns
- fake green runs when repo checks are red

Agent Contracts keeps the scope narrow:

> declare the repo-local contract, enforce it at runtime and in CI, and fail closed with a verdict artifact.

## 5-minute quick start

### 1. Write a coding-agent contract

```yaml
# AGENT_CONTRACT.yaml
agent_contract: "0.1.0"

identity:
  name: repo-build-agent
  version: "0.1.0"
  description: Safe coding/build agent for this repository.

contract:
  postconditions:
    - name: produces_output
      check: "output is not None"
      enforcement: sync_block
      severity: critical

    - name: repo_checks_green
      check: "checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0"
      enforcement: sync_block
      severity: critical

effects:
  authorized:
    filesystem:
      read: ["src/**", "tests/**", "README.md", "pyproject.toml"]
      write: ["src/**", "tests/**", "README.md"]
    shell:
      commands:
        - "python -m pytest *"
        - "python -m ruff check *"
    tools: []
    network: []
    state_writes: []

resources:
  budgets:
    max_tokens: 50000
    max_tool_calls: 20
    max_shell_commands: 10
    max_duration_seconds: 1800

observability:
  run_artifact_path: ".agent-contracts/runs/{run_id}/verdict.json"
```

### 2. Enforce it in the agent runtime

```python
from agent_contracts import ContractEnforcer, load_contract

contract = load_contract("AGENT_CONTRACT.yaml")

with ContractEnforcer(contract, host_name="codex") as enforcer:
    enforcer.check_file_read("src/app.py")
    enforcer.check_file_write("src/app.py")
    enforcer.check_shell_command("python -m pytest tests/test_app.py")

    result = {"status": "done"}

    enforcer.record_check("pytest", "pass", exit_code=0)
    enforcer.record_check("ruff", "pass", exit_code=0)
    verdict = enforcer.finalize_run(output=result)

print(verdict.outcome)      # pass | warn | blocked | fail
print(verdict.artifacts)    # includes verdict artifact path
```

### 3. Gate the verdict in CI

```bash
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml
python -m agent_contracts.cli check-verdict .agent-contracts/runs/<run-id>/verdict.json
```

## Verdict artifacts

Every meaningful run can emit one compact artifact, for example:

```json
{
  "run_id": "...",
  "outcome": "pass",
  "final_gate": "allowed",
  "checks": [
    {"name": "pytest", "status": "pass", "exit_code": 0},
    {"name": "ruff", "status": "pass", "exit_code": 0}
  ],
  "budgets": {
    "tokens": 12345,
    "tool_calls": 0,
    "shell_commands": 2,
    "duration_seconds": 18.2
  },
  "violations": []
}
```

Outcome semantics:

- `pass` — required checks and blocking clauses passed
- `warn` — allowed to proceed, but warnings were recorded
- `blocked` — an operation was denied during the run
- `fail` — the run completed, but required checks or critical postconditions failed

## CLI

```bash
# Validate a contract and show coding/build surfaces
python -m agent_contracts.cli validate AGENT_CONTRACT.yaml

# Check composition compatibility
python -m agent_contracts.cli check-compat producer.yaml consumer.yaml

# Bootstrap from traces
python -m agent_contracts.cli init --from-trace traces.jsonl -o AGENT_CONTRACT.yaml

# Generate a coding-agent starter template
python -m agent_contracts.cli init --template coding

# Gate a verdict artifact in CI
python -m agent_contracts.cli check-verdict .agent-contracts/runs/<run-id>/verdict.json
```

## Host integrations

### Claude Code / Claude SDK

Claude is the strongest local hard-stop path in this repo today because it can deny tool use before execution through hooks. Use the repo contract as the source of truth, and map the contract's allowlists into Claude's hook surface where possible.

### Codex

Codex can use the same repo-local contract for enforcement in wrappers and for final CI gating via verdict artifacts. The contract file stays in the repo; CI becomes the final source of truth for merge readiness.

### OpenAI Agents SDK

The OpenAI adapter can block tool execution at `on_tool_start`, but cannot recover reasoning tokens already spent deciding to call the tool. The docs and adapter are explicit about that limit.

## GitHub Action

```yaml
- uses: pyyush/agentcontracts@v0.2.0
  with:
    contract: AGENT_CONTRACT.yaml
    verdict: .agent-contracts/runs/${{ github.run_id }}/verdict.json
```

The action validates contracts and, when a verdict path is provided, fails the workflow for `blocked` or `fail` outcomes.

## Canonical examples

- `AGENT_CONTRACT.yaml` — canonical repo-build agent contract
- `examples/repo_build_agent.yaml` — reference coding/build repo contract
- `examples/demo_blocked_file_write.yaml` — protected-file demo
- `examples/demo_blocked_command.yaml` — forbidden-command demo
- `examples/demo_failed_checks.yaml` — red-checks demo
- `examples/support_triage.yaml` — broader tier-2 example retained for composition docs

## Project structure

```text
schemas/                          JSON Schema for AGENT_CONTRACT.yaml
spec/SPECIFICATION.md             Human-readable specification
src/agent_contracts/              Python SDK
  cli.py                          CLI entry point
  loader.py                       YAML loading + validation
  types.py                        Dataclasses / type model
  effects.py                      Tool, filesystem, network, and shell authorization
  budgets.py                      Budget tracking
  postconditions.py               Postcondition evaluation
  enforcer.py                     Runtime enforcement + verdict artifacts
  init_from_trace.py              Bootstrap from traces
  adapters/                       Host/framework integrations
examples/                         Reference contracts and demos
action.yml                        GitHub composite action
AGENT_CONTRACT.yaml               Canonical coding-agent contract
```

## Scope and non-goals

This repo is intentionally narrow.

In scope:

- repo-local contracts for coding/build agents
- file, shell, tool, network, and budget boundaries
- runtime + CI gating
- durable verdict artifacts

Out of scope for the current release:

- hosted control planes
- compliance dashboards
- generic agent governance positioning
- speculative multi-agent infrastructure

## License

Apache-2.0
