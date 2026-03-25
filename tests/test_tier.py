"""Tests for tier assessment."""

from __future__ import annotations

from typing import Any, Dict

from agent_contracts.tier import assess_tier, recommend_upgrades


class TestAssessTier:
    def test_tier0_minimal(self, tier0_data: Dict[str, Any]) -> None:
        assert assess_tier(tier0_data) == 0

    def test_tier1_with_inputs(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["inputs"] = {"schema": {"type": "object"}}
        assert assess_tier(tier0_data) == 1

    def test_tier1_with_outputs(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["outputs"] = {"schema": {"type": "object"}}
        assert assess_tier(tier0_data) == 1

    def test_tier1_with_resources(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["resources"] = {"budgets": {"max_cost_usd": 1.0}}
        assert assess_tier(tier0_data) == 1

    def test_tier1_with_authorized_effects(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["effects"] = {"authorized": {"tools": ["search"]}}
        assert assess_tier(tier0_data) == 1

    def test_tier1_full(self, tier1_data: Dict[str, Any]) -> None:
        assert assess_tier(tier1_data) == 1

    def test_tier2_with_failure_model(self, tier1_data: Dict[str, Any]) -> None:
        tier1_data["failure_model"] = {"errors": []}
        assert assess_tier(tier1_data) == 2

    def test_tier2_with_delegation(self, tier1_data: Dict[str, Any]) -> None:
        tier1_data["delegation"] = {"max_depth": 2}
        assert assess_tier(tier1_data) == 2

    def test_tier2_with_declared_effects(self, tier1_data: Dict[str, Any]) -> None:
        tier1_data["effects"]["declared"] = {"tools": ["search"]}
        assert assess_tier(tier1_data) == 2

    def test_tier2_full(self, tier2_data: Dict[str, Any]) -> None:
        assert assess_tier(tier2_data) == 2

    def test_empty_effects_not_tier1(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["effects"] = {}
        assert assess_tier(tier0_data) == 0

    def test_empty_authorized_not_tier1(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["effects"] = {"authorized": {}}
        assert assess_tier(tier0_data) == 0


class TestRecommendUpgrades:
    def test_tier0_recommendations(self, tier0_data: Dict[str, Any]) -> None:
        recs = recommend_upgrades(tier0_data, 0)
        fields = {r.field for r in recs}
        assert "resources.budgets" in fields
        assert "effects.authorized" in fields
        assert all(r.target_tier == 1 for r in recs)

    def test_tier1_recommendations(self, tier1_data: Dict[str, Any]) -> None:
        recs = recommend_upgrades(tier1_data, 1)
        fields = {r.field for r in recs}
        assert "failure_model" in fields
        assert "effects.declared" in fields
        assert all(r.target_tier == 2 for r in recs)

    def test_tier2_no_recommendations(self, tier2_data: Dict[str, Any]) -> None:
        recs = recommend_upgrades(tier2_data, 2)
        assert len(recs) == 0
