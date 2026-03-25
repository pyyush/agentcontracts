"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from click.testing import CliRunner

from agent_contracts.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def contract_file(tmp_path: Path, tier1_data: Dict[str, Any]) -> Path:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return p


class TestValidate:
    def test_valid_contract(self, runner, contract_file) -> None:
        result = runner.invoke(main, ["validate", str(contract_file)])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_valid_contract_json(self, runner, contract_file) -> None:
        result = runner.invoke(main, ["validate", str(contract_file), "--json-output"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["valid"] is True
        assert data["tier"] == 1

    def test_invalid_contract(self, runner, tmp_path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(yaml.dump({"agent_contract": "bad"}, sort_keys=False), encoding="utf-8")
        result = runner.invoke(main, ["validate", str(bad)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_file_not_found(self, runner) -> None:
        result = runner.invoke(main, ["validate", "/nonexistent.yaml"])
        assert result.exit_code != 0

    def test_shows_recommendations(self, runner, tmp_path, tier0_data) -> None:
        p = tmp_path / "tier0.yaml"
        p.write_text(yaml.dump(tier0_data, sort_keys=False), encoding="utf-8")
        result = runner.invoke(main, ["validate", str(p)])
        assert result.exit_code == 0
        assert "Recommendations" in result.output


class TestCheckCompat:
    def test_compatible(self, runner, contract_file) -> None:
        result = runner.invoke(main, ["check-compat", str(contract_file), str(contract_file)])
        assert result.exit_code == 0

    def test_json_output(self, runner, contract_file) -> None:
        result = runner.invoke(main, ["check-compat", str(contract_file), str(contract_file), "-j"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "compatible" in data


class TestInit:
    def test_template_generation(self, runner) -> None:
        result = runner.invoke(main, ["init", "--name", "test-agent"])
        assert result.exit_code == 0
        assert "test-agent" in result.output
        assert "postconditions" in result.output

    def test_output_to_file(self, runner, tmp_path) -> None:
        out = tmp_path / "generated.yaml"
        result = runner.invoke(main, ["init", "--name", "test", "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_from_trace(self, runner, tmp_path) -> None:
        trace_file = tmp_path / "traces.jsonl"
        traces = [
            {"agent": {"name": "trace-agent", "version": "1.0.0"},
             "tool_calls": [{"name": "search"}, {"name": "database.read"}],
             "usage": {"cost_usd": 0.05, "total_tokens": 500},
             "duration_seconds": 2.5},
        ]
        trace_file.write_text(
            "\n".join(__import__("json").dumps(t) for t in traces),
            encoding="utf-8",
        )
        result = runner.invoke(main, ["init", "--from-trace", str(trace_file)])
        assert result.exit_code == 0
        assert "trace-agent" in result.output
        assert "search" in result.output


class TestTestCommand:
    def test_no_eval_suite(self, runner, contract_file) -> None:
        result = runner.invoke(main, ["test", str(contract_file)])
        assert result.exit_code == 0
        assert "Postconditions" in result.output

    def test_with_eval_suite(self, runner, contract_file, tmp_path) -> None:
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        eval_file = eval_dir / "basic.jsonl"
        import json
        cases = [
            {"output": {"status": "ok"}},
            {"output": None},
        ]
        eval_file.write_text(
            "\n".join(json.dumps(c) for c in cases), encoding="utf-8"
        )
        result = runner.invoke(main, ["test", str(contract_file), "--eval-suite", str(eval_dir)])
        # At least one should pass (non-None output), one may fail
        assert "Results:" in result.output
