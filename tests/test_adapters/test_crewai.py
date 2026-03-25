"""Tests for CrewAI adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
import yaml

from agent_contracts.adapters.crewai import ContractGuard
from agent_contracts.enforcer import ContractViolation


@pytest.fixture
def guard(tmp_path: Path, tier1_data: Dict[str, Any]) -> ContractGuard:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return ContractGuard.from_file(p, violation_destination="callback",
                                    violation_callback=lambda e: None)


class TestContractGuard:
    def test_from_file(self, guard) -> None:
        assert guard.enforcer is not None

    def test_validate_inputs(self, guard) -> None:
        errors = guard.validate_inputs({"query": "hello"})
        assert errors == []

    def test_check_authorized_tool(self, guard) -> None:
        guard.check_tool("search")

    def test_check_unauthorized_tool(self, guard) -> None:
        with pytest.raises(ContractViolation):
            guard.check_tool("evil_tool")

    def test_execute_crew(self, guard) -> None:
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "result"
        result = guard.execute(mock_crew, inputs={"query": "test"})
        assert result == "result"
        mock_crew.kickoff.assert_called_once()

    def test_execute_with_invalid_input(self, tmp_path, tier1_data) -> None:
        tier1_data["inputs"]["schema"]["required"] = ["query"]
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
        guard = ContractGuard.from_file(p, violation_destination="callback",
                                         violation_callback=lambda e: None)
        mock_crew = MagicMock()
        with pytest.raises(ContractViolation, match="Input validation"):
            guard.execute(mock_crew, inputs={"wrong_field": "test"})

    def test_wrap_tool(self, guard) -> None:
        def my_tool(x: int) -> int:
            return x * 2

        wrapped = guard.wrap_tool(my_tool, "search")
        assert wrapped(5) == 10

    def test_wrap_unauthorized_tool(self, guard) -> None:
        def my_tool() -> str:
            return "result"

        wrapped = guard.wrap_tool(my_tool, "unauthorized_tool")
        with pytest.raises(ContractViolation):
            wrapped()

    def test_violations_tracked(self, guard) -> None:
        try:
            guard.check_tool("bad")
        except ContractViolation:
            pass
        assert len(guard.violations) == 1
