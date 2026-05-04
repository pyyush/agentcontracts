# Agent Contract Specification v0.1.0

## Overview

An Agent Contract is a repo-local YAML document that declares what an autonomous coding/build agent may do, what it must prove before a run is considered successful, and where the final verdict artifact should be written.

The v0.1.0 surface is intentionally narrow:

- authorize reads, writes, commands, tools, network, and state writes
- enforce resource budgets
- evaluate postconditions against outputs and recorded checks
- emit one durable verdict artifact for each run

## Core principles

1. **Repo-local first** — the contract belongs in the repository.
2. **Fail closed when configured** — coding/build scopes default to deny when present.
3. **One operator-readable verdict** — every meaningful run can end with one artifact.
4. **Host-agnostic core** — the contract is portable across local runtimes and CI.

## File format

Contracts are YAML files, typically named `AGENT_CONTRACT.yaml`.
Unknown fields are ignored for forward compatibility. Extension fields use the `x-` prefix.

```yaml
agent_contract: "0.1.0"
identity:
  name: repo-build-agent
  version: "0.1.0"
contract:
  postconditions:
    - name: produces_output
      check: "output is not None"
```

## Tiers

### Tier 0 — Standalone

Required fields:

- `agent_contract`
- `identity.name`
- `identity.version`
- `contract.postconditions[]`

### Tier 1 — Enforceable

Adds runtime enforcement value:

- `inputs.schema`
- `outputs.schema`
- `effects.authorized`
- `resources.budgets`

Tier 1 is where coding/build guardrails live.

### Tier 2 — Composable

Adds broader composition and observability features:

- `failure_model`
- `effects.declared`
- `delegation`
- `observability`
- `versioning`
- `slo`

## Authorized effects

`effects.authorized` declares what the agent may do.

```yaml
effects:
  authorized:
    tools:
      - search
    network:
      - "https://api.example.com/*"
    state_writes:
      - "tickets.*"
    filesystem:
      read: ["src/**", "tests/**", "README.md"]
      write: ["src/**", "tests/**"]
    shell:
      commands:
        - "python -m pytest *"
        - "python -m ruff check *"
```

Rules:

- tools, network, and state writes are default-deny when configured
- filesystem read/write scopes are default-deny when configured
- filesystem paths are resolved against the repo root before matching; allowlist globs compare only the canonical repo-relative path, so traversal strings such as `src/../.env` do not match `src/**`
- filesystem paths that resolve outside the repo root are denied when filesystem authorization is configured
- shell commands are matched against normalized command strings with glob patterns
- during delegation, authorized effects attenuate by intersection

## Budgets

```yaml
resources:
  budgets:
    max_cost_usd: 1.00
    max_tokens: 50000
    max_tool_calls: 20
    max_shell_commands: 10
    max_duration_seconds: 1800
```

`max_shell_commands` is specific to coding/build workflows and complements tool-call budgets.

## Postconditions and recorded checks

Postconditions are safe expression checks evaluated against `output` plus any extra context provided by the runtime.

```yaml
contract:
  postconditions:
    - name: repo_checks_green
      check: "checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0"
      enforcement: sync_block
      severity: critical
```

Supported expression forms include:

- `output is not None`
- `output.status == "ok"`
- `output.status in ["ok", "warn"]`
- `len(output.items) > 0`
- `checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0`

## Observability and verdict artifacts

```yaml
observability:
  run_artifact_path: ".agent-contracts/runs/{run_id}/verdict.json"
```

The path may contain `{run_id}`.
If omitted, runtimes may default to `.agent-contracts/runs/{run_id}/verdict.json`.

Verdict artifacts include:

- contract identity + spec version
- host identity
- `outcome`: `pass | warn | blocked | fail`
- `final_gate`: `allowed | blocked | failed`
- violations
- executed checks
- budget snapshot
- artifact metadata

## Outcome semantics

- `pass` — required checks and blocking clauses passed
- `warn` — non-blocking warnings were recorded
- `blocked` — an effect or budget violation denied the run in-flight
- `fail` — the run completed, but required checks or critical postconditions failed

## Example coding-agent contract

```yaml
agent_contract: "0.1.0"
identity:
  name: repo-build-agent
  version: "0.1.0"
contract:
  postconditions:
    - name: repo_checks_green
      check: "checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0"
      enforcement: sync_block
      severity: critical
effects:
  authorized:
    filesystem:
      read: ["src/**", "tests/**", "README.md"]
      write: ["src/**", "tests/**"]
    shell:
      commands:
        - "python -m pytest *"
        - "python -m ruff check *"
resources:
  budgets:
    max_shell_commands: 10
observability:
  run_artifact_path: ".agent-contracts/runs/{run_id}/verdict.json"
```

## Compatibility notes

Within v0.1.0:

- adding optional fields is backward-compatible
- removing fields is breaking
- changing field semantics is breaking
- new required fields are breaking

This repo intentionally does **not** use v0.1.0 to broaden into hosted policy platforms or generic agent governance.
