"""Tests for Claude Agent SDK adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
import yaml

from agent_contracts.adapters.claude_agent import ContractHooks
from agent_contracts.schema import validate_verdict_against_schema


@pytest.fixture
def hooks(tmp_path: Path, tier1_data: Dict[str, Any]) -> ContractHooks:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return ContractHooks.from_file(p, violation_destination="callback")


def run_async(coro):
    """Helper to run async tests."""
    return asyncio.run(coro)


class TestContractHooks:
    def test_from_file(self, hooks) -> None:
        assert hooks.enforcer is not None
        assert hooks.enforcer.contract.tier == 1

    def test_authorized_tool_allows(self, hooks) -> None:
        result = run_async(hooks.pre_tool_use({
            "tool_name": "search",
            "tool_input": {},
            "hook_event_name": "PreToolUse",
        }))
        assert result == {}

    def test_unauthorized_tool_denies(self, hooks) -> None:
        result = run_async(hooks.pre_tool_use({
            "tool_name": "delete_all",
            "tool_input": {},
            "hook_event_name": "PreToolUse",
        }))
        assert "hookSpecificOutput" in result
        output = result["hookSpecificOutput"]
        assert output["permissionDecision"] == "deny"
        assert "delete_all" in output["permissionDecisionReason"]
        assert output["hookEventName"] == "PreToolUse"

    def test_deny_includes_contract_name(self, hooks) -> None:
        result = run_async(hooks.pre_tool_use({
            "tool_name": "bad",
            "tool_input": {},
            "hook_event_name": "PreToolUse",
        }))
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "test-agent" in reason

    def test_tool_budget_tracking(self, tmp_path, tier1_data) -> None:
        tier1_data["resources"]["budgets"]["max_tool_calls"] = 2
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
        h = ContractHooks.from_file(p)

        # First two allowed
        run_async(h.pre_tool_use({"tool_name": "search", "tool_input": {}}))
        run_async(h.pre_tool_use({"tool_name": "database.read", "tool_input": {}}))

        # Third denied (budget exceeded — returns deny, not exception)
        result = run_async(h.pre_tool_use({"tool_name": "search", "tool_input": {}}))
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_post_tool_use(self, hooks) -> None:
        result = run_async(hooks.post_tool_use({
            "tool_name": "search",
            "tool_input": {},
        }))
        assert result == {}

    def test_get_hooks_config(self, hooks) -> None:
        config = hooks.get_hooks_config()
        assert "PreToolUse" in config
        assert "PostToolUse" in config
        assert len(config["PreToolUse"]) == 1
        assert hooks.pre_tool_use in config["PreToolUse"][0]["hooks"]

    def test_track_result_cost(self, hooks) -> None:
        msg = MagicMock()
        msg.total_cost_usd = 0.05
        msg.usage = {"input_tokens": 100, "output_tokens": 50}
        hooks.track_result(msg)
        snapshot = hooks.enforcer.budget_tracker.snapshot()
        assert snapshot.cost_usd == 0.05
        assert snapshot.tokens == 150

    def test_track_result_no_cost(self, hooks) -> None:
        msg = MagicMock(spec=[])  # No attributes
        hooks.track_result(msg)  # Should not raise

    def test_track_result_zero_cost(self, hooks) -> None:
        msg = MagicMock()
        msg.total_cost_usd = 0
        msg.usage = {}
        hooks.track_result(msg)

    def test_violations_accumulated(self, hooks) -> None:
        run_async(hooks.pre_tool_use({
            "tool_name": "unauthorized",
            "tool_input": {},
        }))
        assert len(hooks.violations) == 1

    def test_native_shell_effect_is_checked(self, hooks) -> None:
        result = run_async(hooks.pre_tool_use({
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest tests"},
        }))
        assert result == {}

        blocked = run_async(hooks.pre_tool_use({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        }))
        assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Shell command" in blocked["hookSpecificOutput"]["permissionDecisionReason"]

    def test_finalize_pass_verdict_is_schema_valid(self, hooks, tmp_path) -> None:
        verdict = hooks.finalize_run(
            output={"result": "ok"},
            artifact_path=tmp_path / "verdict.json",
        )
        assert verdict.outcome == "pass"
        assert verdict.host["name"] == "claude-agent-sdk"
        assert validate_verdict_against_schema(verdict.to_dict()) == []
        assert (tmp_path / "verdict.json").exists()

    def test_finalize_blocked_verdict_is_schema_valid(self, hooks, tmp_path) -> None:
        run_async(hooks.pre_tool_use({"tool_name": "unauthorized", "tool_input": {}}))

        verdict = hooks.finalize_run(
            output={"result": "ok"},
            artifact_path=tmp_path / "blocked.json",
        )
        assert verdict.outcome == "blocked"
        assert validate_verdict_against_schema(verdict.to_dict()) == []

    def test_finalize_failed_output_verdict_is_schema_valid(self, hooks, tmp_path) -> None:
        verdict = hooks.finalize_run(
            output={"result": 123},
            artifact_path=tmp_path / "failed.json",
        )
        assert verdict.outcome == "fail"
        assert any(check.name == "adapter.output_schema" for check in verdict.checks)
        assert validate_verdict_against_schema(verdict.to_dict()) == []

    def test_finalize_unexpected_error_verdict_is_schema_valid(self, hooks, tmp_path) -> None:
        verdict = hooks.finalize_run(
            execution_error=RuntimeError("boom"),
            artifact_path=tmp_path / "error.json",
        )
        assert verdict.outcome == "fail"
        assert validate_verdict_against_schema(verdict.to_dict()) == []

    def test_finalize_without_observed_output_fails_closed(self, hooks, tmp_path) -> None:
        verdict = hooks.finalize_run(artifact_path=tmp_path / "partial.json")
        assert verdict.outcome == "fail"
        assert any(check.name == "adapter.observed_completion" for check in verdict.checks)
        assert validate_verdict_against_schema(verdict.to_dict()) == []


class TestRealSDKIntegration:
    """Verifies the hooks dict produced by the adapter is consumable by the
    real claude-agent-sdk. Skipped if claude-agent-sdk is not installed
    (it requires Python 3.10+)."""

    def test_hooks_config_accepted_by_sdk(self, hooks) -> None:
        sdk = pytest.importorskip("claude_agent_sdk")
        config = hooks.get_hooks_config()
        # Real SDK exposes ClaudeAgentOptions and accepts a hooks mapping.
        options = sdk.ClaudeAgentOptions(hooks=config)
        assert options.hooks is config

    def test_pre_tool_use_signature_matches_hookcallback(self) -> None:
        sdk = pytest.importorskip("claude_agent_sdk")
        # Adapter callbacks must accept (input_data, tool_use_id, context).
        assert hasattr(sdk, "HookCallback")
        import inspect
        sig = inspect.signature(ContractHooks.pre_tool_use)
        params = list(sig.parameters)
        # self + 3 hook params
        assert params[1:] == ["input_data", "tool_use_id", "context"]
