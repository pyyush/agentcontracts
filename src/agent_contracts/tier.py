"""Tier assessment for Agent Contracts.

Classifies a contract into one of three tiers based on which fields are present:
- Tier 0 (Standalone): identity + postconditions only
- Tier 1 (Enforceable): + input/output schemas, effects.authorized, budgets
- Tier 2 (Composable): + failure_model, effects.declared, delegation, observability, versioning, slo
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

# Fields that upgrade a contract from Tier 0 to Tier 1
_TIER_1_FIELDS = {"inputs", "outputs", "effects", "resources"}

# Fields that upgrade a contract from Tier 1 to Tier 2
_TIER_2_FIELDS = {"failure_model", "delegation", "observability", "versioning", "slo"}


def _has_authorized_effects(data: Dict[str, Any]) -> bool:
    """Check if effects.authorized is present and non-empty."""
    effects = data.get("effects")
    if not isinstance(effects, dict):
        return False
    auth = effects.get("authorized")
    return isinstance(auth, dict) and bool(auth)


def _has_declared_effects(data: Dict[str, Any]) -> bool:
    """Check if effects.declared is present."""
    effects = data.get("effects")
    if not isinstance(effects, dict):
        return False
    return "declared" in effects


def assess_tier(data: Dict[str, Any]) -> int:
    """Determine the tier of a parsed contract YAML.

    Returns 0, 1, or 2.
    """
    has_tier1 = False
    for f in ("inputs", "outputs", "resources"):
        if f in data:
            has_tier1 = True
            break
    if _has_authorized_effects(data):
        has_tier1 = True

    has_tier2 = False
    for f in _TIER_2_FIELDS:
        if f in data:
            has_tier2 = True
            break
    if _has_declared_effects(data):
        has_tier2 = True

    if has_tier2:
        return 2
    if has_tier1:
        return 1
    return 0


@dataclass
class TierRecommendation:
    """A recommendation to add a field for tier upgrade."""

    field: str
    current_tier: int
    target_tier: int
    reason: str


def recommend_upgrades(data: Dict[str, Any], current_tier: int) -> List[TierRecommendation]:
    """Suggest fields to add for the next tier upgrade."""
    recommendations: List[TierRecommendation] = []

    if current_tier == 0:
        if "resources" not in data:
            recommendations.append(
                TierRecommendation(
                    field="resources.budgets",
                    current_tier=0,
                    target_tier=1,
                    reason="Add budget limits (max_cost_usd, max_tokens) for cost control.",
                )
            )
        if not _has_authorized_effects(data):
            recommendations.append(
                TierRecommendation(
                    field="effects.authorized",
                    current_tier=0,
                    target_tier=1,
                    reason="Add a tool allowlist for default-deny effect gating.",
                )
            )
        if "inputs" not in data:
            recommendations.append(
                TierRecommendation(
                    field="inputs.schema",
                    current_tier=0,
                    target_tier=1,
                    reason="Add input schema to reject malformed inputs before execution.",
                )
            )
        if "outputs" not in data:
            recommendations.append(
                TierRecommendation(
                    field="outputs.schema",
                    current_tier=0,
                    target_tier=1,
                    reason="Add output schema to catch schema drift.",
                )
            )

    elif current_tier == 1:
        if "failure_model" not in data:
            recommendations.append(
                TierRecommendation(
                    field="failure_model",
                    current_tier=1,
                    target_tier=2,
                    reason="Add typed errors with retry/fallback to prevent cascading failures.",
                )
            )
        if not _has_declared_effects(data):
            recommendations.append(
                TierRecommendation(
                    field="effects.declared",
                    current_tier=1,
                    target_tier=2,
                    reason="Add effect footprint for audit trails (SOX/HIPAA evidence).",
                )
            )
        if "observability" not in data:
            recommendations.append(
                TierRecommendation(
                    field="observability",
                    current_tier=1,
                    target_tier=2,
                    reason="Add telemetry config for dashboards and canary analysis.",
                )
            )

    return recommendations
