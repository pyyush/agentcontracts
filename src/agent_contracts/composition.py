"""Composition checker — Contract Differential analysis.

Given two contracts (upstream producer and downstream consumer), compute:
- Schema gaps: producer output not assignable to consumer input
- Capability gaps: consumer needs tools not authorized by producer's delegation
- Budget gaps: consumer budget exceeds producer's remaining budget
- Effect validation: declared ⊆ authorized across the composition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_contracts.effects import validate_declared_subset
from agent_contracts.types import Contract


@dataclass
class SchemaGap:
    """A gap between producer output and consumer input schemas."""

    field_path: str
    issue: str


@dataclass
class CapabilityGap:
    """A tool the consumer needs but the producer doesn't authorize for delegation."""

    tool: str
    reason: str


@dataclass
class BudgetGap:
    """A budget field where the consumer exceeds what the producer allows."""

    budget_type: str
    producer_limit: Optional[float]
    consumer_limit: Optional[float]
    issue: str


@dataclass
class CompatibilityReport:
    """Full compatibility report between two contracts."""

    compatible: bool
    producer: str
    consumer: str
    schema_gaps: List[SchemaGap] = field(default_factory=list)
    capability_gaps: List[CapabilityGap] = field(default_factory=list)
    budget_gaps: List[BudgetGap] = field(default_factory=list)
    effect_violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line summary of compatibility."""
        if self.compatible:
            warnings = f" ({len(self.warnings)} warnings)" if self.warnings else ""
            return f"Compatible: {self.producer} -> {self.consumer}{warnings}"
        issues = (
            len(self.schema_gaps)
            + len(self.capability_gaps)
            + len(self.budget_gaps)
            + len(self.effect_violations)
        )
        return f"Incompatible: {self.producer} -> {self.consumer} ({issues} issue(s))"


def _check_schema_compatibility(
    producer_output: Optional[Dict[str, Any]],
    consumer_input: Optional[Dict[str, Any]],
) -> List[SchemaGap]:
    """Check if producer output schema is assignable to consumer input schema.

    This is a structural compatibility check, not full JSON Schema subtyping.
    Checks that required consumer input fields exist in producer output.
    """
    gaps: List[SchemaGap] = []

    if consumer_input is None:
        return gaps  # Consumer accepts anything

    if producer_output is None:
        gaps.append(SchemaGap(
            field_path="(root)",
            issue="Consumer expects structured input but producer has no output schema.",
        ))
        return gaps

    consumer_required = consumer_input.get("required", [])
    producer_props = producer_output.get("properties", {})

    for req_field in consumer_required:
        if req_field not in producer_props:
            gaps.append(SchemaGap(
                field_path=req_field,
                issue=f"Consumer requires field '{req_field}' but producer output schema doesn't define it.",
            ))

    # Check type compatibility for shared fields
    consumer_props = consumer_input.get("properties", {})
    for field_name, consumer_field in consumer_props.items():
        if field_name in producer_props:
            producer_type = producer_props[field_name].get("type")
            consumer_type = consumer_field.get("type")
            if producer_type and consumer_type and producer_type != consumer_type:
                gaps.append(SchemaGap(
                    field_path=field_name,
                    issue=f"Type mismatch: producer outputs '{producer_type}' but consumer expects '{consumer_type}'.",
                ))

    return gaps


def _check_capability_compatibility(
    producer: Contract, consumer: Contract
) -> List[CapabilityGap]:
    """Check if the consumer's tool needs are covered by the producer's delegation."""
    gaps: List[CapabilityGap] = []

    if consumer.effects_authorized is None:
        return gaps

    # If producer has delegation rules, check allowed agents
    if producer.delegation and producer.delegation.allowed_agents is not None:
        if consumer.identity.name not in producer.delegation.allowed_agents:
            gaps.append(CapabilityGap(
                tool="(delegation)",
                reason=f"Consumer '{consumer.identity.name}' not in producer's allowed_agents list.",
            ))

    # If producer has authorized effects and attenuates during delegation,
    # check that consumer's needed tools are within producer's scope
    if producer.effects_authorized and consumer.effects_authorized:
        from agent_contracts.effects import _matches_any

        for tool in consumer.effects_authorized.tools:
            if not _matches_any(tool, producer.effects_authorized.tools):
                gaps.append(CapabilityGap(
                    tool=tool,
                    reason=f"Consumer needs tool '{tool}' but producer doesn't authorize it.",
                ))

    return gaps


def _check_budget_compatibility(
    producer: Contract, consumer: Contract
) -> List[BudgetGap]:
    """Check if consumer budget fits within producer budget."""
    gaps: List[BudgetGap] = []

    if producer.budgets is None or consumer.budgets is None:
        return gaps

    checks = [
        ("max_cost_usd", producer.budgets.max_cost_usd, consumer.budgets.max_cost_usd),
        ("max_tokens", producer.budgets.max_tokens, consumer.budgets.max_tokens),
        ("max_tool_calls", producer.budgets.max_tool_calls, consumer.budgets.max_tool_calls),
        ("max_duration_seconds", producer.budgets.max_duration_seconds, consumer.budgets.max_duration_seconds),
    ]

    for budget_type, prod_limit, cons_limit in checks:
        if prod_limit is not None and cons_limit is not None:
            if cons_limit > prod_limit:
                gaps.append(BudgetGap(
                    budget_type=budget_type,
                    producer_limit=float(prod_limit),
                    consumer_limit=float(cons_limit),
                    issue=f"Consumer {budget_type}={cons_limit} exceeds producer limit={prod_limit}.",
                ))
        elif prod_limit is not None and cons_limit is None:
            gaps.append(BudgetGap(
                budget_type=budget_type,
                producer_limit=float(prod_limit),
                consumer_limit=None,
                issue=f"Producer limits {budget_type}={prod_limit} but consumer has no limit.",
            ))

    return gaps


def check_compatibility(producer: Contract, consumer: Contract) -> CompatibilityReport:
    """Compute the Contract Differential between a producer and consumer.

    Checks schema assignability, capability coverage, budget fit,
    and effect authorization compliance.
    """
    schema_gaps = _check_schema_compatibility(
        producer.output_schema, consumer.input_schema
    )

    capability_gaps = _check_capability_compatibility(producer, consumer)

    budget_gaps = _check_budget_compatibility(producer, consumer)

    effect_violations: List[str] = []
    if consumer.effects_declared and producer.effects_authorized:
        effect_violations = validate_declared_subset(
            consumer.effects_declared, producer.effects_authorized
        )

    warnings: List[str] = []
    if producer.tier < 2:
        warnings.append(f"Producer '{producer.identity.name}' is Tier {producer.tier}; Tier 2 recommended for composition.")
    if consumer.tier < 2:
        warnings.append(f"Consumer '{consumer.identity.name}' is Tier {consumer.tier}; Tier 2 recommended for composition.")

    compatible = (
        len(schema_gaps) == 0
        and len(capability_gaps) == 0
        and len(budget_gaps) == 0
        and len(effect_violations) == 0
    )

    return CompatibilityReport(
        compatible=compatible,
        producer=producer.identity.name,
        consumer=consumer.identity.name,
        schema_gaps=schema_gaps,
        capability_gaps=capability_gaps,
        budget_gaps=budget_gaps,
        effect_violations=effect_violations,
        warnings=warnings,
    )
