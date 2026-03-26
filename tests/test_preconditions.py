"""Tests for precondition evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from agent_contracts.postconditions import (
    PreconditionError,
    PreconditionResult,
    evaluate_preconditions,
)
from agent_contracts.enforcer import ContractEnforcer, ContractViolation
from agent_contracts.loader import load_contract
from agent_contracts.types import PreconditionDef


class TestEvaluatePreconditions:
    def test_passing_precondition(self) -> None:
        pcs = [PreconditionDef(name="has_query", check="input is not None")]
        results = evaluate_preconditions(pcs, {"query": "hello"})
        assert len(results) == 1
        assert results[0].passed is True

    def test_failing_precondition_raises(self) -> None:
        pcs = [PreconditionDef(name="has_query", check="input is None")]
        with pytest.raises(PreconditionError, match="has_query"):
            evaluate_preconditions(pcs, {"query": "hello"})

    def test_failing_precondition_no_raise(self) -> None:
        pcs = [PreconditionDef(name="has_query", check="input is None")]
        results = evaluate_preconditions(pcs, {"query": "hello"}, raise_on_failure=False)
        assert len(results) == 1
        assert results[0].passed is False

    def test_multiple_preconditions(self) -> None:
        pcs = [
            PreconditionDef(name="not_none", check="input is not None"),
            PreconditionDef(name="has_key", check='input.type == "search"'),
        ]
        results = evaluate_preconditions(
            pcs, {"type": "search"}, raise_on_failure=False
        )
        assert all(r.passed for r in results)

    def test_first_failure_stops_on_raise(self) -> None:
        pcs = [
            PreconditionDef(name="fails", check="input is None"),
            PreconditionDef(name="never_reached", check="input is not None"),
        ]
        with pytest.raises(PreconditionError, match="fails"):
            evaluate_preconditions(pcs, "data")

    def test_context_key_is_input(self) -> None:
        pcs = [PreconditionDef(name="check_field", check='input.role == "admin"')]
        results = evaluate_preconditions(
            pcs, {"role": "admin"}, raise_on_failure=False
        )
        assert results[0].passed is True

    def test_precondition_error_attributes(self) -> None:
        pc = PreconditionDef(name="test_pc", check="input is None")
        err = PreconditionError(pc, {"data": 1})
        assert err.precondition is pc
        assert err.input_data == {"data": 1}


class TestEnforcerPreconditions:
    @pytest.fixture
    def contract_with_preconditions(self, tmp_path: Path) -> Any:
        data = {
            "agent_contract": "0.1.0",
            "identity": {"name": "test-agent", "version": "1.0.0"},
            "contract": {
                "postconditions": [
                    {"name": "has_output", "check": "output is not None"}
                ]
            },
            "inputs": {
                "preconditions": [
                    {"name": "has_query", "check": "input is not None"},
                    {"name": "valid_type", "check": 'input.type == "search"'},
                ]
            },
        }
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
        return load_contract(p)

    def test_check_preconditions_pass(self, contract_with_preconditions) -> None:
        enforcer = ContractEnforcer(contract_with_preconditions)
        results = enforcer.check_preconditions({"type": "search"})
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_check_preconditions_fail(self, contract_with_preconditions) -> None:
        enforcer = ContractEnforcer(contract_with_preconditions)
        with pytest.raises(ContractViolation, match="valid_type"):
            enforcer.check_preconditions({"type": "delete"})

    def test_check_preconditions_emits_violation(self, contract_with_preconditions) -> None:
        enforcer = ContractEnforcer(
            contract_with_preconditions, violation_destination="callback"
        )
        with pytest.raises(ContractViolation):
            enforcer.check_preconditions({"type": "delete"})
        assert len(enforcer.violations) == 1
        assert "preconditions" in enforcer.violations[0].violated_clause

    def test_no_preconditions_returns_empty(self, tmp_path) -> None:
        data = {
            "agent_contract": "0.1.0",
            "identity": {"name": "test", "version": "1.0.0"},
            "contract": {
                "postconditions": [
                    {"name": "p", "check": "output is not None"}
                ]
            },
        }
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
        contract = load_contract(p)
        enforcer = ContractEnforcer(contract)
        assert enforcer.check_preconditions({"anything": True}) == []
