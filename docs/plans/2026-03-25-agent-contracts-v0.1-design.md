# Agent Contracts v0.1 — Design Document

## Metadata
- **Status:** Draft
- **Author:** Piyush Vyas
- **Date:** 2026-03-25
- **Reviewers:** Claude quality-reviewer, Codex cross-reviewer
- **Complexity Tier:** Complex

---

## Context & Problem Statement

Production AI agents fail at 41–86.7% rates (MAST taxonomy, 1,642 traces across 7 frameworks).
97% of enterprises with agents in production cannot scale them. The dominant failure modes —
cost runaway, unauthorized tool use, missing audit trails, silent regressions — have no
framework-agnostic solution.

MCP owns transport. LangChain/CrewAI own orchestration. Datadog/Langfuse own observability.
**No layer governs what an agent may do, must guarantee, and what happens when it fails.**

Agent Contracts fills this gap: a YAML spec + validation SDK that enforces agent behavior
at the runtime boundary. The OpenAPI model — a machine-readable document that generates
tooling leverage.

**Why now:** EU AI Act high-risk requirements take effect Aug 2026. HIPAA Security Rule update
makes AI handling ePHI subject to mandatory controls. The standards window closes in 12–18 months.

---

## Goals

1. **Define a YAML spec** (AGENT_CONTRACT.yaml) with 3 graduated tiers (Standalone → Enforceable → Composable)
2. **Ship a Python SDK** (`agent-contracts`) that validates contracts, enforces budgets/effects at runtime, and emits OTel-compatible violation events
3. **Ship a CLI** for validation, compatibility checking, contract generation from traces, and eval testing
4. **Ship framework adapters** for LangChain, CrewAI, and Pydantic AI (each <200 LOC, 3-line integration)
5. **Draft MCP extension proposal** (`x-agent-contract`) for tool-level contract metadata

## Non-Goals

1. **Not a protocol** — MCP owns transport; we layer policy above it
2. **Not a platform** — no hosted service, no vendor lock-in
3. **Not formal verification** — no theorem proving; executable assertions at Levels 2–3
4. **No custom DSL** — YAML primary, CEL-like expressions for inline checks only
5. **No TypeScript SDK** in v0.1 (deferred to v0.1.x, 4–6 weeks post-launch)
6. **No contract registry** — premature infrastructure at zero adoption
7. **No inter-agent negotiation** — requires ecosystem maturity
8. **No taint tracking** — novel; deferred to v0.2

---

## Design

### Option A: Monolithic SDK (Single Package, Everything Built-in)

**Approach:** Single `agent-contracts` package containing spec schema, loader, validator,
enforcer, CLI, OTel emitter, composition checker, and all framework adapters.

**Trade-offs:**
- Pro: Single install, single import, simpler dependency management
- Con: Pulls in framework deps (langchain, crewai, pydanticai) even if unused; bloated install

**Complexity:** ~3000 LOC, 1 package, heavy deps

### Option B: Modular Core + Optional Extras (Recommended)

**Approach:** Core package (`agent-contracts`) with zero required framework deps.
Framework adapters as optional extras (`pip install agent-contracts[langchain]`).
CLI bundled in core. OTel as optional extra.

**Trade-offs:**
- Pro: Minimal install footprint; framework deps only when needed; clean separation of concerns
- Pro: Each module testable independently; easier to maintain
- Con: Slightly more complex packaging (extras_require)

**Complexity:** ~3500 LOC, 1 package with extras, minimal required deps (pyyaml, jsonschema)

### Recommendation

**Option B** — Modular Core + Optional Extras. Matches the plan's "standalone value first" strategy.
A developer gets `pip install agent-contracts` with zero framework baggage. Framework adapters
are opt-in. This mirrors how OpenTelemetry structures its packages.

---

## Detailed Design

### Package Structure

```
agent-contracts/
├── pyproject.toml                    # Package config (hatch build system)
├── LICENSE                           # Apache-2.0
├── README.md                         # Getting started, 5-minute contract
├── AGENT_CONTRACT.yaml               # Reference example (support triage agent)
├── src/
│   └── agent_contracts/
│       ├── __init__.py               # Public API surface
│       ├── py.typed                  # PEP 561 marker
│       ├── types.py                  # Core data models (dataclasses)
│       ├── schema.py                 # JSON Schema definitions (all 3 tiers)
│       ├── loader.py                 # YAML loading + schema validation
│       ├── tier.py                   # Tier assessment logic
│       ├── enforcer.py               # Runtime enforcement (budgets, effects, schemas)
│       ├── effects.py                # Effect authorization (default-deny allowlist)
│       ├── budgets.py                # Budget tracking (cost, tokens, tool calls, duration)
│       ├── postconditions.py         # Postcondition evaluation (sync/async/monitor)
│       ├── violations.py             # Violation event creation + OTel emission
│       ├── composition.py            # Contract Differential (schema/capability/budget gaps)
│       ├── cli.py                    # CLI entry point (click-based)
│       ├── init_from_trace.py        # Generate contract skeleton from traces
│       ├── _version.py               # Version constant
│       └── adapters/
│           ├── __init__.py
│           ├── langchain.py          # LangChain adapter (<200 LOC)
│           ├── crewai.py             # CrewAI adapter (<200 LOC)
│           └── pydantic_ai.py        # Pydantic AI adapter (<200 LOC)
├── schemas/
│   └── agent-contract.schema.json    # The JSON Schema (machine-readable spec)
├── spec/
│   └── SPECIFICATION.md              # Human-readable spec narrative
├── mcp/
│   └── x-agent-contract.md           # MCP extension proposal
├── examples/
│   ├── support_triage.yaml           # Tier 2 reference example
│   ├── simple_chatbot.yaml           # Tier 0 minimal example
│   └── cost_controlled.yaml          # Tier 1 budget-focused example
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Shared fixtures
    ├── test_loader.py                # Contract loading + validation
    ├── test_tier.py                  # Tier assessment
    ├── test_enforcer.py              # Runtime enforcement
    ├── test_effects.py               # Effect authorization
    ├── test_budgets.py               # Budget tracking
    ├── test_postconditions.py        # Postcondition evaluation
    ├── test_violations.py            # Violation events
    ├── test_composition.py           # Contract Differential
    ├── test_cli.py                   # CLI commands
    ├── test_init_from_trace.py       # Trace-based generation
    └── test_adapters/
        ├── test_langchain.py
        ├── test_crewai.py
        └── test_pydantic_ai.py
```

### Core Data Models (`types.py`)

```python
@dataclass(frozen=True)
class ContractIdentity:
    name: str
    version: str

@dataclass(frozen=True)
class PostconditionDef:
    name: str
    check: str  # CEL-like expression or "eval:judge" reference
    enforcement: Literal["sync_block", "sync_warn", "async_monitor"]
    severity: Literal["critical", "major", "minor"]
    slo: SLODef | None = None

@dataclass(frozen=True)
class EffectsAuthorized:
    tools: list[str]  # Allowlist (default: deny all)
    network: list[str]  # URL patterns
    state_writes: list[str]  # State scope patterns

@dataclass(frozen=True)
class EffectsDeclared:
    tools: list[str]  # Actual effect footprint
    network: list[str]
    state_writes: list[str]

@dataclass(frozen=True)
class ResourceBudgets:
    max_cost_usd: float | None
    max_tokens: int | None
    max_tool_calls: int | None
    max_duration_seconds: float | None

@dataclass(frozen=True)
class Contract:
    spec_version: str
    identity: ContractIdentity
    postconditions: list[PostconditionDef]
    tier: int  # Computed: 0, 1, or 2
    # Tier 1
    input_schema: dict | None
    output_schema: dict | None
    effects_authorized: EffectsAuthorized | None
    budgets: ResourceBudgets | None
    # Tier 2
    failure_model: dict | None
    effects_declared: EffectsDeclared | None
    delegation: DelegationRules | None
    observability: ObservabilityConfig | None
    versioning: VersioningConfig | None
    slo: SLOConfig | None
```

### Enforcement Flow (`enforcer.py`)

```
Agent invocation
  │
  ├─ PRE: validate input against input_schema (Tier 1)
  │
  ├─ DURING: intercept each tool call
  │   ├─ Check tool name against effects.authorized.tools (default: DENY)
  │   ├─ Increment tool_call counter → check against max_tool_calls
  │   ├─ Accumulate cost → check against max_cost_usd
  │   ├─ Check elapsed time → check against max_duration_seconds
  │   └─ On violation → emit OTel event, circuit-break or warn
  │
  ├─ POST: validate output against output_schema (Tier 1)
  │   ├─ Evaluate sync_block postconditions → block if failed
  │   ├─ Evaluate sync_warn postconditions → warn if failed
  │   └─ Queue async_monitor postconditions → evaluate async
  │
  └─ EMIT: violation events (OTel-compatible)
```

Three usage patterns:
1. **Decorator:** `@enforce_contract("path/to/contract.yaml")`
2. **Context Manager:** `with ContractEnforcer(contract) as enforcer:`
3. **Explicit API:** `enforcer.check_tool_call(name, args)`, `enforcer.validate_output(data)`

### Effect Authorization (`effects.py`)

- **Default-deny:** If `effects.authorized.tools` is defined, only listed tools are allowed
- **Pattern matching:** Supports glob patterns (`database.*`, `api.user.*`)
- **Composition:** During delegation, authorized effects compose via **intersection** (capabilities attenuate)
- **Audit:** Declared effects compose via **union** (footprint accumulates)
- Runtime enforces: `declared ⊆ authorized`

### Budget Enforcement (`budgets.py`)

- Per-invocation counters: cost, tokens, tool_calls, elapsed time
- Thread-safe (uses threading.Lock for counter updates)
- Circuit breaker: when threshold hit, raises `BudgetExceededError`
- Cost tracking: accepts cost callbacks from the caller (we don't hardcode model prices)

### Violation Events (`violations.py`)

OTel-compatible structured events:
```python
@dataclass
class ViolationEvent:
    contract_id: str
    contract_version: str
    violated_clause: str  # e.g., "budgets.max_cost_usd"
    evidence: dict  # e.g., {"actual": 5.23, "limit": 5.00}
    severity: str  # "critical", "major", "minor"
    enforcement: str  # "blocked", "warned", "monitored"
    trace_id: str | None
    span_id: str | None
    timestamp: str  # ISO 8601
```

Emitters: stdout (default), OTel SDK (when `opentelemetry-api` installed), callback.

### Composition Checker (`composition.py`)

Contract Differential between two Tier 2 contracts:
- **Schema gaps:** Input schema A not assignable to output schema B
- **Capability gaps:** A requires tools not authorized by B
- **Budget gaps:** A's budget exceeds B's budget
- **Effect validation:** A's declared effects not ⊆ B's authorized effects
- Returns structured report with compatibility verdict

### CLI (`cli.py`)

Built on `click`. Four commands:
- `validate`: Load contract, validate schema, report tier, recommend missing fields
- `check-compat`: Run composition checker between two contracts
- `init`: Generate contract skeleton from execution trace JSONL
- `test`: Run eval suite against contract postconditions

---

## Security & Privacy Considerations

- [x] **Default-deny effects** — tools not in allowlist are blocked before execution
- [x] **No prompt-level enforcement** — all enforcement at SDK layer (not bypassable via injection)
- [x] **Budget circuit breakers** — prevent cost runaway architecturally
- [x] **No secrets in contracts** — contracts are declarative policy, no credentials
- [x] **Input validation** — all YAML input validated against JSON Schema before processing
- [x] **No eval()** — CEL-like expressions parsed by a safe evaluator, never `eval()`
- [x] **Thread-safe counters** — budget enforcement is concurrency-safe
- [x] **Immutable data models** — `frozen=True` dataclasses prevent mutation after construction

---

## Testing Strategy

### Unit Tests
- Loader: valid/invalid YAML, schema validation errors, partial contracts
- Tier: correct tier classification for all combinations of fields
- Enforcer: tool call interception, budget tracking, input/output validation
- Effects: allowlist matching, glob patterns, default-deny, composition (intersection/union)
- Budgets: counter increments, threshold detection, thread safety
- Postconditions: sync_block/sync_warn/async_monitor evaluation
- Violations: event creation, OTel formatting, callback emission
- Composition: schema compatibility, capability gaps, budget gaps

### Integration Tests
- Full enforcement flow: load contract → enforce agent invocation → collect violations
- CLI commands: validate, check-compat, init from sample traces
- Framework adapters: integration with mocked LangChain/CrewAI/Pydantic AI hooks

### Test Coverage Target
- 90%+ line coverage on core modules (loader, enforcer, effects, budgets)
- 80%+ on adapters and CLI

---

## Monitoring & Observability

- **Built-in:** Violation events are the core observability primitive
- **OTel integration:** Events conform to OpenTelemetry semantic conventions
- **Metrics:** contract_satisfaction_rate, budget_utilization, effect_violations_total
- N/A for self-monitoring — this is the monitoring SDK, not a monitored service

---

## Rollback Plan

- [x] Change is revertable with `git revert` (all commits on feature branch)
- [x] No data migrations
- [x] Not applicable (new repo, no production deployment)
- [x] Rollback: `pip uninstall agent-contracts`

---

## Dependencies & Risks

### Required Dependencies (minimal)
- `pyyaml>=6.0` — YAML parsing
- `jsonschema>=4.20` — JSON Schema validation
- `click>=8.0` — CLI framework

### Optional Dependencies
- `opentelemetry-api>=1.20` — OTel event emission
- `langchain-core>=0.2` — LangChain adapter
- `crewai>=0.50` — CrewAI adapter
- `pydantic-ai>=0.1` — Pydantic AI adapter

### Risks
- **Adoption stalls at Tier 0** (medium) — mitigated by CLI nudges toward Tier 1
- **CEL expression parser complexity** — mitigated by starting with simple comparisons only
- **Framework adapter API changes** — mitigated by pinning minimum versions, thin wrappers

---

## Approval

- [ ] Design reviewed by quality reviewer
- [ ] Design reviewed by cross-reviewer (DADS, Complex tier)
- [ ] Security considerations reviewed
- [ ] Testing strategy adequate for risk level
