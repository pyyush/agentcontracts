# Agent Contract Specification v0.1.0

## Overview

An Agent Contract is a YAML document that declares what an agent **must do**,
**must not do**, and **what happens when it fails**. Contracts are enforced
at the runtime boundary by the SDK — never via prompts.

Contracts follow the **OpenAPI model**: a machine-readable document that
generates tooling leverage. Write a YAML file. Get cost control, tool-use
security, and audit trails.

## File Format

Contracts are YAML files, typically named `AGENT_CONTRACT.yaml`. The SDK
also accepts any `.yaml` or `.yml` file. A JSON Schema is provided at
`schemas/agent-contract.schema.json` for editor support and machine validation.

### Forward Compatibility

- Unknown fields are **ignored** (must-ignore semantics)
- Extension fields use the `x-` prefix (e.g., `x-hipaa-compliance: true`)
- Spec version (`agent_contract` field) follows semver

---

## Three Tiers

Contracts use graduated tiers. Start simple, add guarantees as production demands.

### Tier 0: Standalone (4 fields)

**Purpose:** Self-documentation + local validation. Value without any runtime.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_contract` | semver string | Yes | Spec version (e.g., `"0.1.0"`) |
| `identity.name` | string | Yes | Unique agent identifier |
| `identity.version` | semver string | Yes | Agent implementation version |
| `contract.postconditions[]` | array (min 1) | Yes | Machine-checkable output guarantees |

A Tier 0 contract is useful on its own: it documents what the agent guarantees
and can be validated locally with `aicontracts validate`.

### Tier 1: Enforceable (adds runtime value)

Everything in Tier 0, plus:

| Field | What It Solves |
|-------|---------------|
| `inputs.schema` | Reject malformed inputs before execution (JSON Schema) |
| `outputs.schema` | Validate structured output, catch schema drift (JSON Schema) |
| `effects.authorized` | Default-deny tool allowlist + network + state writes |
| `resources.budgets` | `max_cost_usd`, `max_tokens`, `max_tool_calls`, `max_duration_seconds` |

The SDK enforces Tier 1 fields at the boundary: input validation, tool gating,
budget circuit breakers, and output validation.

### Tier 2: Composable (adds multi-agent + compliance value)

Everything in Tier 1, plus:

| Field | What It Solves |
|-------|---------------|
| `failure_model` | Typed errors with retry/fallback semantics |
| `effects.declared` | Effect footprint for audit trails (composes via union) |
| `delegation` | Max depth, attenuation rules, sub-agent requirements |
| `observability` | Required OTel spans/events + violation event schema |
| `versioning` | Content-addressed build ID + breaking change rules |
| `slo` | Target rates for contract satisfaction, latency, cost |

---

## Field Reference

### `agent_contract` (required)

```yaml
agent_contract: "0.1.0"
```

Spec version. Enables forward compatibility.

### `identity` (required)

```yaml
identity:
  name: support-triage-agent
  version: "2.1.0"
  description: Triages support tickets by priority.
  authors:
    - Piyush Vyas
```

### `contract.postconditions` (required, min 1)

```yaml
contract:
  postconditions:
    - name: valid_priority
      check: 'output.priority in ["critical", "high", "medium", "low"]'
      enforcement: sync_block    # sync_block | sync_warn | async_monitor
      severity: critical         # critical | major | minor
      description: Priority must be valid.
      slo:
        target_rate: 0.995
        window: "24h"
```

**Enforcement timing:**
- `sync_block`: Fails the invocation if the check fails
- `sync_warn`: Logs a warning, emits a violation event, but allows the result
- `async_monitor`: Deferred evaluation (e.g., LLM-as-judge quality checks)

**Check syntax:** CEL-like expressions evaluated safely (no `eval()`):
- `output is not None`
- `output.status == "resolved"`
- `output.status in ["resolved", "escalated"]`
- `len(output.items) > 0`
- `output.score >= 0.8`
- `eval:judge` (LLM-as-judge, async only in v0.1)

### `effects` (Tier 1+)

```yaml
effects:
  authorized:       # Capability scope — what the agent MAY do
    tools:
      - search
      - database.*   # Glob patterns supported
    network:
      - "https://api.example.com/*"
    state_writes:
      - "tickets.*"

  declared:          # Effect footprint — what actually happens (Tier 2)
    tools:
      - search
    network:
      - "https://api.example.com/search"
    state_writes:
      - "tickets.priority"
```

**Key rules:**
- `effects.authorized` is **default-deny**: tools not listed are blocked
- During delegation, authorized effects compose via **intersection** (capabilities attenuate)
- Declared effects compose via **union** (footprint accumulates)
- Runtime enforces: `declared ⊆ authorized`

### `resources.budgets` (Tier 1+)

```yaml
resources:
  budgets:
    max_cost_usd: 0.50
    max_tokens: 15000
    max_tool_calls: 20
    max_duration_seconds: 30.0
```

Per-invocation limits. The SDK trips a circuit breaker when any threshold is exceeded.

### `failure_model` (Tier 2)

```yaml
failure_model:
  errors:
    - name: timeout
      retryable: true
      max_retries: 3
    - name: rate_limit
      retryable: true
      max_retries: 2
      fallback: queue-agent
  default_timeout_seconds: 30.0
  circuit_breaker:
    failure_threshold: 5
    reset_timeout_seconds: 60.0
```

### `delegation` (Tier 2)

```yaml
delegation:
  max_depth: 2
  attenuate_effects: true     # Intersect authorized effects during delegation
  require_contract: true      # Sub-agents must have their own contract
  allowed_agents:
    - cache-agent
    - summarizer
```

### `observability` (Tier 2)

```yaml
observability:
  traces:
    enabled: true
    sample_rate: 1.0
  metrics:
    - name: latency_ms
      type: histogram
  violation_events:
    emit: true
    destination: otel   # stdout | otel | callback
```

### `versioning` (Tier 2)

```yaml
versioning:
  build_id: "sha256:abc123..."
  breaking_changes: []
  substitution:
    compatible_with:
      - "1.0.0"
```

### `slo` (Tier 2)

```yaml
slo:
  contract_satisfaction_rate:
    target: 0.995
    window: "24h"
  latency:
    p50_ms: 500
    p99_ms: 5000
  cost:
    avg_usd: 0.10
    p99_usd: 0.50
  error_budget_policy: freeze_deployments
```

---

## Breaking Change Rules

For the v0.x series:
- Adding optional fields is **not** a breaking change
- Removing or renaming fields **is** a breaking change
- Changing field semantics **is** a breaking change
- Adding new required fields **is** a breaking change

From v1.0 onward: no breaking changes within a major version.

---

## Positioning

| Layer | What It Does | What Contracts Add |
|-------|-------------|-------------------|
| **MCP** | Tool transport (JSON-RPC) | Policy layer above transport |
| **Agent Skills** | Capability discovery (Markdown) | Machine-enforceable guarantees |
| **A2A** | Agent discovery and routing | Behavioral guarantees on routes |
| **AWS AgentCore** | Cedar policy enforcement | Portable, open spec |
| **LangChain/CrewAI** | Agent orchestration | Declarative, out-of-process enforcement |
| **OpenAPI** | Structural API contracts | Behavioral contracts for non-deterministic agents |
