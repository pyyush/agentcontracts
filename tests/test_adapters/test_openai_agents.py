"""Tests for OpenAI Agents SDK adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
import yaml

from agent_contracts.adapters.openai_agents import ContractRunHooks
from agent_contracts.enforcer import ContractViolation


@pytest.fixture
def hooks(tmp_path: Path, tier1_data: Dict[str, Any]) -> ContractRunHooks:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return ContractRunHooks.from_file(
        p, violation_destination="callback", raise_on_violation=True
    )


def run_async(coro):
    """Helper to run async tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestContractRunHooks:
    def test_from_file(self, hooks) -> None:
        assert hooks.enforcer is not None
        assert hooks.enforcer.contract.tier == 1

    def test_authorized_tool_passes(self, hooks) -> None:
        tool = MagicMock()
        tool.name = "search"
        run_async(hooks.on_tool_start(None, None, tool))

    def test_unauthorized_tool_raises(self, hooks) -> None:
        tool = MagicMock()
        tool.name = "delete_all"
        with pytest.raises(ContractViolation, match="not authorized"):
            run_async(hooks.on_tool_start(None, None, tool))

    def test_tool_budget_tracking(self, tmp_path, tier1_data) -> None:
        tier1_data["resources"]["budgets"]["max_tool_calls"] = 2
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
        h = ContractRunHooks.from_file(p, raise_on_violation=True)

        tool = MagicMock()
        tool.name = "search"
        run_async(h.on_tool_start(None, None, tool))
        tool.name = "database.read"
        run_async(h.on_tool_start(None, None, tool))

        tool.name = "search"
        with pytest.raises(ContractViolation):
            run_async(h.on_tool_start(None, None, tool))

    def test_token_tracking_from_llm_end(self, hooks) -> None:
        response = MagicMock()
        response.usage.total_tokens = 500
        run_async(hooks.on_llm_end(None, None, response))
        assert hooks.enforcer.budget_tracker.snapshot().tokens == 500

    def test_token_tracking_no_usage(self, hooks) -> None:
        response = MagicMock(spec=[])  # No usage attr
        run_async(hooks.on_llm_end(None, None, response))

    def test_postconditions_on_agent_end(self, hooks) -> None:
        run_async(hooks.on_agent_end(None, None, {"result": "data"}))

    def test_violations_accumulated(self, hooks) -> None:
        tool = MagicMock()
        tool.name = "bad_tool"
        try:
            run_async(hooks.on_tool_start(None, None, tool))
        except ContractViolation:
            pass
        assert len(hooks.violations) == 1

    def test_non_raising_mode(self, tmp_path, tier1_data) -> None:
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
        h = ContractRunHooks.from_file(p, raise_on_violation=False)
        tool = MagicMock()
        tool.name = "unauthorized"
        run_async(h.on_tool_start(None, None, tool))  # Should not raise

    def test_on_tool_end(self, hooks) -> None:
        run_async(hooks.on_tool_end(None, None, None, "result"))

    def test_on_agent_start(self, hooks) -> None:
        run_async(hooks.on_agent_start(None, None))

    def test_on_handoff(self, hooks) -> None:
        run_async(hooks.on_handoff(None, None))

    def test_on_llm_start(self, hooks) -> None:
        run_async(hooks.on_llm_start(None, None, None, None))
