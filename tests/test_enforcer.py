"""Tests for the runtime enforcer."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from agent_contracts.enforcer import ContractEnforcer, ContractViolation, enforce_contract
from agent_contracts.loader import load_contract


@pytest.fixture
def enforcer_tier1(tmp_yaml, tier1_data: Dict[str, Any]):
    """ContractEnforcer with a Tier 1 contract."""
    path = tmp_yaml(tier1_data)
    contract = load_contract(path)
    return ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: None)


class TestContractEnforcer:
    def test_authorized_tool_passes(self, enforcer_tier1) -> None:
        enforcer_tier1.check_tool_call("search")  # In allowlist

    def test_unauthorized_tool_raises(self, enforcer_tier1) -> None:
        with pytest.raises(ContractViolation, match="not authorized"):
            enforcer_tier1.check_tool_call("delete_everything")

    def test_tool_call_budget(self, tmp_yaml, tier1_data) -> None:
        tier1_data["resources"]["budgets"]["max_tool_calls"] = 2
        path = tmp_yaml(tier1_data)
        contract = load_contract(path)
        enforcer = ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: None)
        enforcer.check_tool_call("search")
        enforcer.check_tool_call("database.read")
        with pytest.raises(ContractViolation, match="tool_calls"):
            enforcer.check_tool_call("search")

    def test_cost_budget(self, enforcer_tier1) -> None:
        enforcer_tier1.add_cost(0.30)
        enforcer_tier1.add_cost(0.15)
        with pytest.raises(ContractViolation, match="cost_usd"):
            enforcer_tier1.add_cost(0.10)  # Total 0.55 > 0.50 limit

    def test_token_budget(self, tmp_yaml, tier1_data) -> None:
        tier1_data["resources"]["budgets"]["max_tokens"] = 1000
        path = tmp_yaml(tier1_data)
        contract = load_contract(path)
        enforcer = ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: None)
        enforcer.add_tokens(800)
        with pytest.raises(ContractViolation, match="tokens"):
            enforcer.add_tokens(300)

    def test_input_validation(self, enforcer_tier1) -> None:
        errors = enforcer_tier1.validate_input({"query": "hello"})
        assert errors == []

    def test_input_validation_failure(self, enforcer_tier1) -> None:
        errors = enforcer_tier1.validate_input({"query": 123})  # Should be string
        assert len(errors) > 0

    def test_output_validation(self, enforcer_tier1) -> None:
        errors = enforcer_tier1.validate_output({"result": "answer"})
        assert errors == []

    def test_postcondition_evaluation(self, enforcer_tier1) -> None:
        results = enforcer_tier1.evaluate_postconditions({"status": "ok"})
        assert len(results) == 1
        assert results[0].passed is True

    def test_violations_accumulated(self, tmp_yaml, tier1_data) -> None:
        path = tmp_yaml(tier1_data)
        contract = load_contract(path)
        events = []
        enforcer = ContractEnforcer(
            contract, violation_destination="callback", violation_callback=lambda e: events.append(e)
        )
        try:
            enforcer.check_tool_call("unauthorized_tool")
        except ContractViolation:
            pass
        assert len(enforcer.violations) == 1

    def test_context_manager(self, tmp_yaml, tier1_data) -> None:
        path = tmp_yaml(tier1_data)
        contract = load_contract(path)
        with ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: None) as enforcer:
            enforcer.check_tool_call("search")

    def test_no_effects_allows_all(self, tmp_yaml, tier0_data) -> None:
        path = tmp_yaml(tier0_data)
        contract = load_contract(path)
        enforcer = ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: None)
        enforcer.check_tool_call("anything")  # No effects configured = allow all


class TestEnforceContractDecorator:
    def test_decorator_basic(self, tmp_yaml, tier0_data) -> None:
        path = tmp_yaml(tier0_data)

        @enforce_contract(str(path), violation_destination="callback")
        def my_agent(query: str, _enforcer: Any = None) -> str:
            return "result"

        result = my_agent("hello")
        assert result == "result"

    def test_decorator_postcondition_fail(self, tmp_yaml) -> None:
        data = {
            "agent_contract": "0.1.0",
            "identity": {"name": "strict-agent", "version": "1.0.0"},
            "contract": {
                "postconditions": [
                    {"name": "not_none", "check": "output is not None", "enforcement": "sync_block"}
                ]
            },
        }
        path = tmp_yaml(data)

        @enforce_contract(str(path), violation_destination="callback")
        def bad_agent(query: str, _enforcer: Any = None) -> None:
            return None

        from agent_contracts.postconditions import PostconditionError

        with pytest.raises(PostconditionError):
            bad_agent("hello")
