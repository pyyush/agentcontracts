"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from click.testing import CliRunner

from agent_contracts.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def contract_file(tmp_path: Path, tier1_data: Dict[str, Any]) -> Path:
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return path


class TestValidate:
    def test_valid_contract(self, runner: CliRunner, contract_file: Path) -> None:
        result = runner.invoke(main, ["validate", str(contract_file)])
        assert result.exit_code == 0
        assert "PASSED" in result.output
        assert "Coding/build surfaces" in result.output

    def test_valid_contract_json(self, runner: CliRunner, contract_file: Path) -> None:
        result = runner.invoke(main, ["validate", str(contract_file), "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is True
        assert data["tier"] == 1
        assert data["coding_surfaces"]["filesystem_write"] == ["src/**", "tests/**"]

    def test_invalid_contract(self, runner: CliRunner, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(yaml.dump({"agent_contract": "bad"}, sort_keys=False), encoding="utf-8")
        result = runner.invoke(main, ["validate", str(bad)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_shows_recommendations(self, runner: CliRunner, tmp_path: Path, tier0_data: Dict[str, Any]) -> None:
        path = tmp_path / "tier0.yaml"
        path.write_text(yaml.dump(tier0_data, sort_keys=False), encoding="utf-8")
        result = runner.invoke(main, ["validate", str(path)])
        assert result.exit_code == 0
        assert "Recommendations" in result.output


class TestCheckCompat:
    def test_compatible(self, runner: CliRunner, contract_file: Path) -> None:
        result = runner.invoke(main, ["check-compat", str(contract_file), str(contract_file)])
        assert result.exit_code == 0

    def test_json_output(self, runner: CliRunner, contract_file: Path) -> None:
        result = runner.invoke(main, ["check-compat", str(contract_file), str(contract_file), "-j"])
        assert result.exit_code == 0
        assert "compatible" in json.loads(result.output)


class TestInit:
    def test_template_generation(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["init", "--name", "test-agent"])
        assert result.exit_code == 0
        assert "test-agent" in result.output
        assert "postconditions" in result.output

    def test_coding_template_generation(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["init", "--template", "coding"])
        assert result.exit_code == 0
        assert "filesystem:" in result.output
        assert "run_artifact_path" in result.output

    def test_output_to_file(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "generated.yaml"
        result = runner.invoke(main, ["init", "--name", "test", "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_from_trace(self, runner: CliRunner, tmp_path: Path) -> None:
        trace_file = tmp_path / "traces.jsonl"
        traces = [
            {
                "agent": {"name": "trace-agent", "version": "1.0.0"},
                "tool_calls": [{"name": "search"}, {"name": "database.read"}],
                "shell_commands": ["python -m pytest tests/test_app.py"],
                "filesystem": {"read": ["src/app.py"], "write": ["tests/test_app.py"]},
                "usage": {"cost_usd": 0.05, "total_tokens": 500},
                "duration_seconds": 2.5,
            },
        ]
        trace_file.write_text("\n".join(json.dumps(t) for t in traces), encoding="utf-8")
        result = runner.invoke(main, ["init", "--from-trace", str(trace_file)])
        assert result.exit_code == 0
        assert "trace-agent" in result.output
        assert "filesystem" in result.output
        assert "shell" in result.output


class TestCheckVerdict:
    def test_pass(self, runner: CliRunner, tmp_path: Path) -> None:
        verdict = tmp_path / "verdict.json"
        verdict.write_text(json.dumps({"outcome": "pass", "final_gate": "allowed", "checks": []}), encoding="utf-8")
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 0
        assert "Outcome: pass" in result.output

    def test_fail(self, runner: CliRunner, tmp_path: Path) -> None:
        verdict = tmp_path / "verdict.json"
        verdict.write_text(json.dumps({"outcome": "fail", "final_gate": "failed", "checks": []}), encoding="utf-8")
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1


class TestTestCommand:
    def test_no_eval_suite(self, runner: CliRunner, contract_file: Path) -> None:
        result = runner.invoke(main, ["test", str(contract_file)])
        assert result.exit_code == 0
        assert "Postconditions" in result.output

    def test_with_eval_suite(self, runner: CliRunner, contract_file: Path, tmp_path: Path) -> None:
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        eval_file = eval_dir / "basic.jsonl"
        eval_file.write_text("\n".join(json.dumps(c) for c in [{"output": {"status": "ok"}}, {"output": None}]), encoding="utf-8")
        result = runner.invoke(main, ["test", str(contract_file), "--eval-suite", str(eval_dir)])
        assert "Results:" in result.output
