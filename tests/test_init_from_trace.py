"""Tests for trace-based contract generation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from agent_contracts.init_from_trace import (
    generate_contract_from_traces,
    generate_contract_yaml,
)


class TestGenerateFromTraces:
    def _write_traces(self, tmp_path: Path, traces: list) -> Path:
        p = tmp_path / "traces.jsonl"
        p.write_text("\n".join(json.dumps(t) for t in traces), encoding="utf-8")
        return p

    def test_extracts_tools(self, tmp_path: Path) -> None:
        traces = [
            {"tool_calls": [{"name": "search"}, {"name": "database.read"}]},
            {"tool_calls": [{"name": "search"}, {"name": "api.call"}]},
        ]
        path = self._write_traces(tmp_path, traces)
        result = generate_contract_from_traces(path)
        tools = result["effects"]["authorized"]["tools"]
        assert "search" in tools
        assert "database.read" in tools
        assert "api.call" in tools

    def test_extracts_budgets(self, tmp_path: Path) -> None:
        traces = [
            {"usage": {"cost_usd": 0.10, "total_tokens": 1000}, "duration_seconds": 5.0,
             "tool_calls": [{"name": "a"}, {"name": "b"}]},
            {"usage": {"cost_usd": 0.20, "total_tokens": 2000}, "duration_seconds": 10.0,
             "tool_calls": [{"name": "a"}]},
        ]
        path = self._write_traces(tmp_path, traces)
        result = generate_contract_from_traces(path)
        budgets = result["resources"]["budgets"]
        assert budgets["max_cost_usd"] == 0.24  # 0.20 * 1.2
        assert budgets["max_tokens"] == 2400  # 2000 * 1.2

    def test_extracts_identity(self, tmp_path: Path) -> None:
        traces = [{"agent": {"name": "my-agent", "version": "2.0.0"}, "tool_calls": []}]
        path = self._write_traces(tmp_path, traces)
        result = generate_contract_from_traces(path)
        assert result["identity"]["name"] == "my-agent"
        assert result["identity"]["version"] == "2.0.0"

    def test_name_override(self, tmp_path: Path) -> None:
        traces = [{"agent": {"name": "original", "version": "1.0.0"}, "tool_calls": []}]
        path = self._write_traces(tmp_path, traces)
        result = generate_contract_from_traces(path, agent_name="override")
        assert result["identity"]["name"] == "override"

    def test_always_has_postcondition(self, tmp_path: Path) -> None:
        traces = [{"tool_calls": []}]
        path = self._write_traces(tmp_path, traces)
        result = generate_contract_from_traces(path)
        assert len(result["contract"]["postconditions"]) >= 1

    def test_yaml_output(self, tmp_path: Path) -> None:
        traces = [{"tool_calls": [{"name": "search"}], "usage": {"cost_usd": 0.01, "total_tokens": 100}}]
        path = self._write_traces(tmp_path, traces)
        yaml_str = generate_contract_yaml(path)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["agent_contract"] == "0.1.0"

    def test_empty_traces(self, tmp_path: Path) -> None:
        path = self._write_traces(tmp_path, [])
        result = generate_contract_from_traces(path)
        assert result["identity"]["name"] == "unnamed-agent"
        assert "effects" not in result  # No tools observed
