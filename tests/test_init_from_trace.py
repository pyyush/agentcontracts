"""Tests for trace-based contract generation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from agent_contracts.init_from_trace import generate_contract_from_traces, generate_contract_yaml


class TestGenerateFromTraces:
    def _write_traces(self, tmp_path: Path, traces: list) -> Path:
        path = tmp_path / "traces.jsonl"
        path.write_text("\n".join(json.dumps(t) for t in traces), encoding="utf-8")
        return path

    def test_extracts_tools(self, tmp_path: Path) -> None:
        traces = [
            {"tool_calls": [{"name": "search"}, {"name": "database.read"}]},
            {"tool_calls": [{"name": "search"}, {"name": "api.call"}]},
        ]
        result = generate_contract_from_traces(self._write_traces(tmp_path, traces))
        tools = result["effects"]["authorized"]["tools"]
        assert "search" in tools
        assert "database.read" in tools
        assert "api.call" in tools

    def test_extracts_filesystem_and_shell(self, tmp_path: Path) -> None:
        traces = [
            {
                "filesystem": {"read": ["src/app.py"], "write": ["tests/test_app.py"]},
                "shell_commands": ["python -m pytest tests/test_app.py"],
            }
        ]
        result = generate_contract_from_traces(self._write_traces(tmp_path, traces))
        authorized = result["effects"]["authorized"]
        assert authorized["filesystem"]["read"] == ["src/**"]
        assert authorized["filesystem"]["write"] == ["tests/**"]
        assert authorized["shell"]["commands"] == ["python -m pytest tests/test_app.py"]

    def test_extracts_budgets(self, tmp_path: Path) -> None:
        traces = [
            {"usage": {"cost_usd": 0.10, "total_tokens": 1000}, "duration_seconds": 5.0, "tool_calls": [{"name": "a"}, {"name": "b"}], "shell_commands": ["pytest"]},
            {"usage": {"cost_usd": 0.20, "total_tokens": 2000}, "duration_seconds": 10.0, "tool_calls": [{"name": "a"}], "shell_commands": ["pytest", "ruff"]},
        ]
        result = generate_contract_from_traces(self._write_traces(tmp_path, traces))
        budgets = result["resources"]["budgets"]
        assert budgets["max_cost_usd"] == 0.24
        assert budgets["max_tokens"] == 2400
        assert budgets["max_shell_commands"] == 3

    def test_extracts_identity(self, tmp_path: Path) -> None:
        traces = [{"agent": {"name": "my-agent", "version": "2.0.0"}, "tool_calls": []}]
        result = generate_contract_from_traces(self._write_traces(tmp_path, traces))
        assert result["identity"]["name"] == "my-agent"
        assert result["identity"]["version"] == "2.0.0"

    def test_name_override(self, tmp_path: Path) -> None:
        traces = [{"agent": {"name": "original", "version": "1.0.0"}, "tool_calls": []}]
        result = generate_contract_from_traces(self._write_traces(tmp_path, traces), agent_name="override")
        assert result["identity"]["name"] == "override"

    def test_always_has_postcondition(self, tmp_path: Path) -> None:
        result = generate_contract_from_traces(self._write_traces(tmp_path, [{"tool_calls": []}]))
        assert len(result["contract"]["postconditions"]) >= 1

    def test_yaml_output(self, tmp_path: Path) -> None:
        traces = [{"tool_calls": [{"name": "search"}], "usage": {"cost_usd": 0.01, "total_tokens": 100}}]
        parsed = yaml.safe_load(generate_contract_yaml(self._write_traces(tmp_path, traces)))
        assert parsed["agent_contract"] == "0.1.0"
        assert parsed["observability"]["run_artifact_path"] == ".agent-contracts/runs/{run_id}/verdict.json"

    def test_empty_traces(self, tmp_path: Path) -> None:
        result = generate_contract_from_traces(self._write_traces(tmp_path, []))
        assert result["identity"]["name"] == "unnamed-agent"
        assert "effects" in result
