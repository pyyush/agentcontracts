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


@pytest.fixture
def verdict_payload() -> Dict[str, Any]:
    return {
        "run_id": "run-123",
        "contract": {
            "name": "test-agent",
            "version": "1.0.0",
            "spec_version": "0.1.0",
        },
        "host": {"name": "pytest", "version": "1.0.0"},
        "outcome": "pass",
        "final_gate": "allowed",
        "violations": [],
        "checks": [
            {
                "name": "pytest",
                "status": "pass",
                "required": True,
                "exit_code": 0,
                "detail": "passed",
                "evidence": {"command": "python3 -m pytest"},
            }
        ],
        "budgets": {
            "cost_usd": 0.0,
            "tokens": 0,
            "tool_calls": 0,
            "shell_commands": 0,
            "duration_seconds": 0.1,
        },
        "artifacts": {"verdict_path": ".agent-contracts/runs/run-123/verdict.json"},
        "timestamp": "2026-05-04T00:00:00+00:00",
        "warnings": [],
    }


def _write_verdict(tmp_path: Path, payload: Dict[str, Any]) -> Path:
    verdict = tmp_path / "verdict.json"
    verdict.write_text(json.dumps(payload), encoding="utf-8")
    return verdict


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
        parsed = yaml.safe_load(result.output)
        assert parsed["agent_contract"] == "1.0.0"
        assert parsed["identity"]["name"] == "test-agent"
        assert parsed["identity"]["version"] == "1.0.0"
        assert "postconditions" in parsed["contract"]

    def test_coding_template_generation(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["init", "--template", "coding"])
        assert result.exit_code == 0
        parsed = yaml.safe_load(result.output)
        assert parsed["agent_contract"] == "1.0.0"
        assert parsed["identity"]["version"] == "1.0.0"
        assert "filesystem" in parsed["effects"]["authorized"]
        assert "run_artifact_path" in parsed["observability"]

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
        parsed = yaml.safe_load(result.output)
        assert parsed["agent_contract"] == "1.0.0"
        assert parsed["identity"] == {"name": "trace-agent", "version": "1.0.0"}
        assert "filesystem" in parsed["effects"]["authorized"]
        assert "shell" in parsed["effects"]["authorized"]


class TestCheckVerdict:
    def test_pass(self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]) -> None:
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 0
        assert "Outcome: pass" in result.output

    def test_warn(self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]) -> None:
        verdict_payload["outcome"] = "warn"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 0
        assert "Outcome: warn" in result.output

    def test_warn_fail_on_warn(
        self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]
    ) -> None:
        verdict_payload["outcome"] = "warn"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict), "--fail-on-warn"])
        assert result.exit_code == 1
        assert "Outcome: warn" in result.output

    def test_warn_json_fail_on_warn(
        self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]
    ) -> None:
        verdict_payload["outcome"] = "warn"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(
            main, ["check-verdict", str(verdict), "--json-output", "--fail-on-warn"]
        )
        assert result.exit_code == 1
        assert json.loads(result.output)["outcome"] == "warn"

    def test_blocked(self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]) -> None:
        verdict_payload["outcome"] = "blocked"
        verdict_payload["final_gate"] = "blocked"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1
        assert "Outcome: blocked" in result.output

    def test_fail(self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]) -> None:
        verdict_payload["outcome"] = "fail"
        verdict_payload["final_gate"] = "failed"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1

    def test_malformed_json(self, runner: CliRunner, tmp_path: Path) -> None:
        verdict = tmp_path / "verdict.json"
        verdict.write_text("{not-json", encoding="utf-8")
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1
        assert "Verdict JSON error" in result.output

    def test_missing_required_fields(self, runner: CliRunner, tmp_path: Path) -> None:
        verdict = _write_verdict(tmp_path, {"outcome": "pass", "final_gate": "allowed"})
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1
        assert "Verdict schema error" in result.output
        assert "run_id" in result.output

    def test_missing_required_fields_json_output(self, runner: CliRunner, tmp_path: Path) -> None:
        verdict = _write_verdict(tmp_path, {"outcome": "pass", "final_gate": "allowed"})
        result = runner.invoke(main, ["check-verdict", str(verdict), "--json-output"])
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["valid"] is False
        assert any("run_id" in error for error in payload["errors"])

    def test_invalid_outcome(self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]) -> None:
        verdict_payload["outcome"] = "green"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1
        assert "Verdict schema error" in result.output
        assert "outcome" in result.output

    def test_invalid_outcome_gate_pair(
        self, runner: CliRunner, tmp_path: Path, verdict_payload: Dict[str, Any]
    ) -> None:
        verdict_payload["outcome"] = "pass"
        verdict_payload["final_gate"] = "blocked"
        verdict = _write_verdict(tmp_path, verdict_payload)
        result = runner.invoke(main, ["check-verdict", str(verdict)])
        assert result.exit_code == 1
        assert "Verdict schema error" in result.output
        assert "final_gate" in result.output


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
