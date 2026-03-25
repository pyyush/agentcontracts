# MCP Extension Proposal: `x-agent-contract`

**Status:** Draft
**Author:** Piyush Vyas
**Date:** 2026-03-25
**Target:** MCP tool definitions (optional, non-breaking extension)

## Summary

This proposal adds an optional `x-agent-contract` extension field to MCP tool
definitions. It attaches preconditions, effect declarations, and trust-level
metadata to tool schemas at discovery time — enabling contract-aware agents to
make informed decisions about tool usage without modifying MCP itself.

## Motivation

MCP defines **how** agents discover and invoke tools via JSON-RPC. It does not
define:

- **Preconditions:** What must be true before a tool is called
- **Effect declarations:** What side effects a tool produces
- **Trust levels:** How much authority a tool requires
- **Cost metadata:** How expensive a tool invocation is

Agent Contracts fill this gap by attaching behavioral metadata to tool schemas.
This enables agents with contracts to:

1. Skip tools that violate their authorized effects
2. Estimate budget impact before tool invocation
3. Verify preconditions before calling (reducing wasted calls)
4. Build audit trails of tool usage with declared effects

## Specification

### Extension Field

```json
{
  "name": "database_write",
  "description": "Write a record to the database",
  "inputSchema": { ... },
  "x-agent-contract": {
    "preconditions": [
      {
        "name": "record_valid",
        "check": "input.record_id is not None",
        "description": "Record ID must be provided"
      }
    ],
    "effects": {
      "type": "state_write",
      "scope": "database.records",
      "reversible": true,
      "description": "Writes a record to the database"
    },
    "trust_level": "elevated",
    "estimated_cost": {
      "tokens": 500,
      "latency_ms": 200,
      "usd": 0.001
    },
    "rate_limits": {
      "max_calls_per_minute": 60,
      "max_calls_per_hour": 1000
    }
  }
}
```

### Field Definitions

#### `x-agent-contract.preconditions`

Array of precondition objects. Each has:
- `name` (string, required): Precondition identifier
- `check` (string, required): CEL-like expression
- `description` (string, optional): Human-readable explanation

#### `x-agent-contract.effects`

Effect declaration for the tool:
- `type` (string): `"read"`, `"state_write"`, `"network"`, `"notification"`, `"deletion"`
- `scope` (string): Dot-notation scope (e.g., `"database.records"`)
- `reversible` (boolean): Whether the effect can be undone
- `description` (string): Human-readable effect description

#### `x-agent-contract.trust_level`

One of:
- `"standard"`: No special authority required
- `"elevated"`: Requires explicit authorization (e.g., writes)
- `"critical"`: Requires approval gate (e.g., deletion, payment)

#### `x-agent-contract.estimated_cost`

Cost metadata for budget estimation:
- `tokens` (integer): Estimated token consumption
- `latency_ms` (integer): Estimated latency
- `usd` (number): Estimated cost in USD

#### `x-agent-contract.rate_limits`

Rate limit metadata:
- `max_calls_per_minute` (integer)
- `max_calls_per_hour` (integer)

## Integration with Agent Contracts SDK

When an agent with a contract discovers MCP tools:

1. **Effect filtering:** The SDK reads `x-agent-contract.effects` and filters
   tools whose effects are not in the agent's `effects.authorized` scope
2. **Budget estimation:** The SDK sums `estimated_cost` for planned tool calls
   and checks against `resources.budgets`
3. **Precondition validation:** Before calling a tool, the SDK evaluates
   `preconditions` to avoid wasted calls
4. **Trust gate:** Tools with `trust_level: "critical"` require explicit
   approval if the agent's delegation rules require it

## Backward Compatibility

- This is an **optional extension** — MCP servers that don't include
  `x-agent-contract` work normally
- MCP clients that don't understand `x-agent-contract` ignore it
  (standard JSON must-ignore semantics)
- No changes to MCP's JSON-RPC protocol, transport, or core schema

## Next Steps

1. Circulate informally with MCP community members
2. Gather feedback on field names and semantics
3. Submit as a formal extension proposal to the Agentic AI Foundation
4. Build reference implementation in the Agent Contracts Python SDK
