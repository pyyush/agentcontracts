"""Tests for composition checker."""

from __future__ import annotations

from typing import Any, Dict

from agent_contracts.composition import check_compatibility
from agent_contracts.loader import load_contract


class TestCheckCompatibility:
    def test_compatible_contracts(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        # Add consumer-agent to producer's allowed_agents
        tier2_data["delegation"]["allowed_agents"].append("consumer-agent")
        consumer_data = {
            **tier2_data,
            "identity": {"name": "consumer-agent", "version": "1.0.0"},
            "inputs": {"schema": {"type": "object", "properties": {"result": {"type": "string"}}}},
            "effects": {
                "authorized": {"tools": ["search"], "network": [], "state_writes": []},
                "declared": {"tools": ["search"], "network": [], "state_writes": []},
            },
            "resources": {"budgets": {"max_cost_usd": 0.25, "max_tokens": 5000, "max_tool_calls": 10, "max_duration_seconds": 15.0}},
            "delegation": {
                "max_depth": 1,
                "allowed_agents": [],
            },
        }
        producer_path = tmp_yaml(tier2_data, "producer.yaml")
        consumer_path = tmp_yaml(consumer_data, "consumer.yaml")
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
        report = check_compatibility(producer, consumer)
        assert report.compatible is True
        assert "Compatible" in report.summary()

    def test_schema_gap_missing_field(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        consumer_data = {
            **tier2_data,
            "identity": {"name": "consumer", "version": "1.0.0"},
            "inputs": {
                "schema": {
                    "type": "object",
                    "required": ["magic_field"],
                    "properties": {"magic_field": {"type": "string"}},
                }
            },
        }
        producer_path = tmp_yaml(tier2_data, "producer.yaml")
        consumer_path = tmp_yaml(consumer_data, "consumer.yaml")
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
        report = check_compatibility(producer, consumer)
        assert not report.compatible
        assert len(report.schema_gaps) >= 1
        assert any("magic_field" in g.issue for g in report.schema_gaps)

    def test_capability_gap_tool(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        consumer_data = {
            **tier2_data,
            "identity": {"name": "consumer", "version": "1.0.0"},
            "effects": {
                "authorized": {"tools": ["search", "admin.delete"], "network": [], "state_writes": []},
                "declared": {"tools": ["search"], "network": [], "state_writes": []},
            },
        }
        producer_path = tmp_yaml(tier2_data, "producer.yaml")
        consumer_path = tmp_yaml(consumer_data, "consumer.yaml")
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
        report = check_compatibility(producer, consumer)
        assert not report.compatible
        assert any(g.tool == "admin.delete" for g in report.capability_gaps)

    def test_budget_gap(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        consumer_data = {
            **tier2_data,
            "identity": {"name": "consumer", "version": "1.0.0"},
            "resources": {"budgets": {"max_cost_usd": 100.0, "max_tokens": 10000}},
        }
        producer_path = tmp_yaml(tier2_data, "producer.yaml")
        consumer_path = tmp_yaml(consumer_data, "consumer.yaml")
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
        report = check_compatibility(producer, consumer)
        assert not report.compatible
        assert any(g.budget_type == "max_cost_usd" for g in report.budget_gaps)

    def test_effect_violation(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        consumer_data = {
            **tier2_data,
            "identity": {"name": "consumer", "version": "1.0.0"},
            "effects": {
                "authorized": {"tools": ["search"], "network": [], "state_writes": []},
                "declared": {"tools": ["search", "evil_tool"], "network": [], "state_writes": []},
            },
        }
        producer_path = tmp_yaml(tier2_data, "producer.yaml")
        consumer_path = tmp_yaml(consumer_data, "consumer.yaml")
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
        report = check_compatibility(producer, consumer)
        assert not report.compatible
        assert len(report.effect_violations) >= 1

    def test_tier_warnings(self, tmp_yaml, tier0_data: Dict[str, Any]) -> None:
        producer_path = tmp_yaml(tier0_data, "producer.yaml")
        consumer_path = tmp_yaml(tier0_data, "consumer.yaml")
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
        report = check_compatibility(producer, consumer)
        assert len(report.warnings) >= 1
        assert any("Tier 0" in w for w in report.warnings)

    def test_summary_format(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        path = tmp_yaml(tier2_data)
        c = load_contract(path)
        report = check_compatibility(c, c)
        summary = report.summary()
        assert "test-agent" in summary
