"""Tests for contract loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from agent_contracts.loader import (
    ContractLoadError,
    load_contract,
    load_contract_yaml,
    validate_contract,
)


class TestLoadContractYaml:
    def test_load_valid_yaml(self, tmp_yaml, tier0_data: Dict[str, Any]) -> None:
        path = tmp_yaml(tier0_data)
        result = load_contract_yaml(path)
        assert result["identity"]["name"] == "test-agent"

    def test_file_not_found(self) -> None:
        with pytest.raises(ContractLoadError, match="not found"):
            load_contract_yaml("/nonexistent/path.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(":\n  invalid: [yaml\n", encoding="utf-8")
        with pytest.raises(ContractLoadError, match="YAML parse error"):
            load_contract_yaml(bad)

    def test_non_mapping_yaml(self, tmp_path: Path) -> None:
        scalar = tmp_path / "scalar.yaml"
        scalar.write_text("just a string", encoding="utf-8")
        with pytest.raises(ContractLoadError, match="must be a YAML mapping"):
            load_contract_yaml(scalar)


class TestValidateContract:
    def test_valid_tier0(self, tier0_data: Dict[str, Any]) -> None:
        errors = validate_contract(tier0_data)
        assert errors == []

    def test_valid_tier1(self, tier1_data: Dict[str, Any]) -> None:
        errors = validate_contract(tier1_data)
        assert errors == []

    def test_valid_tier2(self, tier2_data: Dict[str, Any]) -> None:
        errors = validate_contract(tier2_data)
        assert errors == []

    def test_missing_identity(self) -> None:
        data = {
            "agent_contract": "0.1.0",
            "contract": {"postconditions": [{"name": "x", "check": "true"}]},
        }
        errors = validate_contract(data)
        assert any("identity" in e for e in errors)

    def test_missing_postconditions(self) -> None:
        data = {
            "agent_contract": "0.1.0",
            "identity": {"name": "a", "version": "1.0.0"},
            "contract": {"postconditions": []},
        }
        errors = validate_contract(data)
        assert any("postconditions" in e for e in errors)

    def test_invalid_version_format(self) -> None:
        data = {
            "agent_contract": "not-semver",
            "identity": {"name": "a", "version": "1.0.0"},
            "contract": {"postconditions": [{"name": "x", "check": "true"}]},
        }
        errors = validate_contract(data)
        assert any("agent_contract" in e for e in errors)

    def test_x_extension_allowed(self, tier0_data: Dict[str, Any]) -> None:
        tier0_data["x-custom-field"] = {"hello": "world"}
        errors = validate_contract(tier0_data)
        assert errors == []


class TestLoadContract:
    def test_load_tier0(self, tmp_yaml, tier0_data: Dict[str, Any]) -> None:
        path = tmp_yaml(tier0_data)
        contract = load_contract(path)
        assert contract.tier == 0
        assert contract.identity.name == "test-agent"
        assert contract.identity.version == "1.0.0"
        assert len(contract.postconditions) == 1
        assert contract.postconditions[0].name == "has_output"

    def test_load_tier1(self, tmp_yaml, tier1_data: Dict[str, Any]) -> None:
        path = tmp_yaml(tier1_data)
        contract = load_contract(path)
        assert contract.tier == 1
        assert contract.budgets is not None
        assert contract.budgets.max_cost_usd == 0.50
        assert contract.effects_authorized is not None
        assert "search" in contract.effects_authorized.tools

    def test_load_tier2(self, tmp_yaml, tier2_data: Dict[str, Any]) -> None:
        path = tmp_yaml(tier2_data)
        contract = load_contract(path)
        assert contract.tier == 2
        assert contract.failure_model is not None
        assert len(contract.failure_model.errors) == 2
        assert contract.delegation is not None
        assert contract.delegation.max_depth == 2
        assert contract.effects_declared is not None
        assert contract.slo is not None
        assert contract.slo.contract_satisfaction_rate is not None
        assert contract.slo.contract_satisfaction_rate.target == 0.995

    def test_strict_validation_raises(self, tmp_yaml) -> None:
        bad_data = {"agent_contract": "bad", "identity": {"name": "a"}}
        path = tmp_yaml(bad_data)
        with pytest.raises(ContractLoadError, match="validation failed"):
            load_contract(path, strict=True)

    def test_non_strict_returns_partial(self, tmp_yaml) -> None:
        partial = {
            "agent_contract": "0.1.0",
            "identity": {"name": "partial", "version": "0.0.1"},
            "contract": {"postconditions": [{"name": "x", "check": "true"}]},
        }
        path = tmp_yaml(partial)
        contract = load_contract(path, strict=False)
        assert contract.identity.name == "partial"

    def test_raw_preserved(self, tmp_yaml, tier0_data: Dict[str, Any]) -> None:
        tier0_data["x-custom"] = "value"
        path = tmp_yaml(tier0_data)
        contract = load_contract(path)
        assert contract.raw is not None
        assert contract.raw["x-custom"] == "value"
