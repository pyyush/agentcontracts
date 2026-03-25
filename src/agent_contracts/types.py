"""Core data models for Agent Contracts.

All models are frozen dataclasses — immutable after construction.
Uses Optional and Union for Python 3.9 compatibility (no X | Y syntax).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


# --- Tier 0: Standalone ---


@dataclass(frozen=True)
class ContractIdentity:
    """Unique agent identifier and version."""

    name: str
    version: str
    description: Optional[str] = None
    authors: Optional[List[str]] = None


@dataclass(frozen=True)
class PostconditionSLO:
    """SLO clause for a postcondition — aggregate tracking over a rolling window."""

    target_rate: Optional[float] = None
    window: Optional[str] = None


@dataclass(frozen=True)
class PostconditionDef:
    """A machine-checkable output guarantee with enforcement timing."""

    name: str
    check: str
    enforcement: Literal["sync_block", "sync_warn", "async_monitor"] = "sync_warn"
    severity: Literal["critical", "major", "minor"] = "major"
    description: Optional[str] = None
    slo: Optional[PostconditionSLO] = None


# --- Tier 1: Enforceable ---


@dataclass(frozen=True)
class EffectsAuthorized:
    """Capability scope — what the agent MAY do (default: deny all).

    Composes via intersection during delegation.
    """

    tools: List[str] = field(default_factory=list)
    network: List[str] = field(default_factory=list)
    state_writes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResourceBudgets:
    """Per-invocation resource limits. Circuit breaker trips on threshold."""

    max_cost_usd: Optional[float] = None
    max_tokens: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_duration_seconds: Optional[float] = None


@dataclass(frozen=True)
class PreconditionDef:
    """A precondition that must hold before the agent runs."""

    name: str
    check: str
    description: Optional[str] = None


# --- Tier 2: Composable ---


@dataclass(frozen=True)
class EffectsDeclared:
    """Effect footprint — what side effects actually occur.

    Composes via union for auditing. Runtime enforces declared ⊆ authorized.
    """

    tools: List[str] = field(default_factory=list)
    network: List[str] = field(default_factory=list)
    state_writes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ErrorDef:
    """A typed error with retry and fallback semantics."""

    name: str
    retryable: bool = False
    max_retries: int = 0
    fallback: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Circuit breaker configuration for failure model."""

    failure_threshold: int = 5
    reset_timeout_seconds: float = 60.0


@dataclass(frozen=True)
class FailureModel:
    """Typed errors with retry/fallback semantics."""

    errors: List[ErrorDef] = field(default_factory=list)
    default_timeout_seconds: Optional[float] = None
    circuit_breaker: Optional[CircuitBreakerConfig] = None


@dataclass(frozen=True)
class DelegationRules:
    """Rules for delegating work to sub-agents."""

    max_depth: int = 3
    attenuate_effects: bool = True
    require_contract: bool = False
    allowed_agents: Optional[List[str]] = None


@dataclass(frozen=True)
class MetricDef:
    """A metric to emit for observability."""

    name: str
    type: Literal["counter", "histogram", "gauge"]
    description: Optional[str] = None


@dataclass(frozen=True)
class TracesConfig:
    """Trace sampling configuration."""

    enabled: bool = True
    sample_rate: float = 1.0


@dataclass(frozen=True)
class ViolationEventsConfig:
    """How violation events are emitted."""

    emit: bool = True
    destination: Literal["stdout", "otel", "callback"] = "stdout"


@dataclass(frozen=True)
class ObservabilityConfig:
    """Required telemetry configuration."""

    traces: Optional[TracesConfig] = None
    metrics: List[MetricDef] = field(default_factory=list)
    violation_events: Optional[ViolationEventsConfig] = None


@dataclass(frozen=True)
class SubstitutionConfig:
    """Liskov-style substitution compatibility."""

    compatible_with: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class VersioningConfig:
    """Content-addressed build identification and breaking change rules."""

    build_id: Optional[str] = None
    breaking_changes: List[str] = field(default_factory=list)
    substitution: Optional[SubstitutionConfig] = None


@dataclass(frozen=True)
class ContractSatisfactionSLO:
    """SLO for aggregate contract satisfaction."""

    target: Optional[float] = None
    window: Optional[str] = None


@dataclass(frozen=True)
class LatencySLO:
    """Latency SLO targets."""

    p50_ms: Optional[float] = None
    p99_ms: Optional[float] = None


@dataclass(frozen=True)
class CostSLO:
    """Cost SLO targets."""

    avg_usd: Optional[float] = None
    p99_usd: Optional[float] = None


@dataclass(frozen=True)
class SLOConfig:
    """Service Level Objectives for aggregate contract satisfaction."""

    contract_satisfaction_rate: Optional[ContractSatisfactionSLO] = None
    latency: Optional[LatencySLO] = None
    cost: Optional[CostSLO] = None
    error_budget_policy: Optional[str] = None


@dataclass(frozen=True)
class Contract:
    """A complete agent contract — the primary data model.

    Tier is computed from which fields are present:
    - Tier 0: identity + postconditions (minimum valid contract)
    - Tier 1: + input/output schemas, effects.authorized, budgets
    - Tier 2: + failure_model, effects.declared, delegation, observability, versioning, slo
    """

    spec_version: str
    identity: ContractIdentity
    postconditions: List[PostconditionDef]
    tier: int  # Computed by tier assessor

    # Tier 1
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    preconditions: Optional[List[PreconditionDef]] = None
    effects_authorized: Optional[EffectsAuthorized] = None
    budgets: Optional[ResourceBudgets] = None

    # Tier 2
    failure_model: Optional[FailureModel] = None
    effects_declared: Optional[EffectsDeclared] = None
    delegation: Optional[DelegationRules] = None
    observability: Optional[ObservabilityConfig] = None
    versioning: Optional[VersioningConfig] = None
    slo: Optional[SLOConfig] = None

    # Raw data (preserves x- extensions and unknown fields)
    raw: Optional[Dict[str, Any]] = field(default=None, repr=False)
