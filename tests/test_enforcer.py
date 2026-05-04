"""Tests for the runtime enforcer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from agent_contracts.enforcer import (
    ContractEnforcer,
    ContractViolation,
    enforce_contract,
    load_verdict_artifact,
)
from agent_contracts.loader import load_contract
from agent_contracts.postconditions import PostconditionError


@pytest.fixture
def enforcer_tier1(tmp_yaml, tier1_data: Dict[str, Any]):
    contract = load_contract(tmp_yaml(tier1_data))
    return ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: None)


@pytest.fixture
def coding_contract_data() -> Dict[str, Any]:
    return {
        "agent_contract": "0.1.0",
        "identity": {"name": "repo-build-agent", "version": "0.1.0"},
        "contract": {
            "postconditions": [
                {
                    "name": "repo_checks_green",
                    "check": "checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0",
                    "enforcement": "sync_block",
                    "severity": "critical",
                }
            ]
        },
        "effects": {
            "authorized": {
                "tools": [],
                "network": [],
                "state_writes": [],
                "filesystem": {
                    "read": ["src/**", "tests/**", "README.md"],
                    "write": ["src/**"],
                },
                "shell": {"commands": ["python -m pytest *"]},
            }
        },
        "resources": {"budgets": {"max_shell_commands": 1}},
        "observability": {"run_artifact_path": ".agent-contracts/runs/{run_id}/verdict.json"},
    }


class TestContractEnforcer:
    def test_authorized_tool_passes(self, enforcer_tier1) -> None:
        enforcer_tier1.check_tool_call("search")

    def test_unauthorized_tool_raises(self, enforcer_tier1) -> None:
        with pytest.raises(ContractViolation, match="not authorized"):
            enforcer_tier1.check_tool_call("delete_everything")

    def test_file_write_blocked(self, tmp_yaml, coding_contract_data, tmp_path: Path) -> None:
        contract_path = tmp_yaml(coding_contract_data)
        contract = load_contract(contract_path)
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)
        with pytest.raises(ContractViolation, match="File write"):
            enforcer.check_file_write("tests/test_app.py")
        verdict = enforcer.finalize_run()
        assert verdict.outcome == "blocked"
        assert Path(verdict.artifacts["verdict_path"]).exists()
        loaded = load_verdict_artifact(verdict.artifacts["verdict_path"])
        assert loaded["outcome"] == "blocked"

    def test_file_write_blocked_when_filesystem_authorization_omitted(
        self, tmp_yaml, coding_contract_data, tmp_path: Path
    ) -> None:
        del coding_contract_data["effects"]["authorized"]["filesystem"]
        contract = load_contract(tmp_yaml(coding_contract_data))
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)

        with pytest.raises(ContractViolation, match="File write"):
            enforcer.check_file_write("src/app.py")

        verdict = enforcer.finalize_run()
        assert verdict.outcome == "blocked"
        assert verdict.violations[0]["violated_clause"] == "effects.authorized.filesystem.write"

    def test_shell_command_blocked(self, tmp_yaml, coding_contract_data, tmp_path: Path) -> None:
        contract = load_contract(tmp_yaml(coding_contract_data))
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)
        with pytest.raises(ContractViolation, match="Shell command"):
            enforcer.check_shell_command("python -m mypy src")
        assert enforcer.finalize_run().outcome == "blocked"

    def test_shell_command_blocked_when_shell_authorization_omitted(
        self, tmp_yaml, coding_contract_data, tmp_path: Path
    ) -> None:
        del coding_contract_data["effects"]["authorized"]["shell"]
        contract = load_contract(tmp_yaml(coding_contract_data))
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)

        with pytest.raises(ContractViolation, match="Shell command"):
            enforcer.check_shell_command("python -m pytest tests/test_app.py")

        verdict = enforcer.finalize_run()
        assert verdict.outcome == "blocked"
        assert verdict.violations[0]["violated_clause"] == "effects.authorized.shell.commands"

    def test_shell_command_budget(self, tmp_yaml, coding_contract_data, tmp_path: Path) -> None:
        contract = load_contract(tmp_yaml(coding_contract_data))
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)
        enforcer.check_shell_command("python -m pytest tests/test_app.py")
        with pytest.raises(ContractViolation, match="shell_commands"):
            enforcer.check_shell_command("python -m pytest tests/test_other.py")

    def test_fail_verdict_when_required_checks_fail(self, tmp_yaml, coding_contract_data, tmp_path: Path) -> None:
        contract = load_contract(tmp_yaml(coding_contract_data))
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)
        enforcer.record_check("pytest", "fail", exit_code=1)
        enforcer.record_check("ruff", "pass", exit_code=0)
        verdict = enforcer.finalize_run(output={"status": "done"})
        assert verdict.outcome == "fail"
        assert verdict.final_gate == "failed"
        assert any(v["violated_clause"] == "contract.postconditions.repo_checks_green" for v in verdict.violations)

    def test_pass_verdict_writes_artifact(self, tmp_yaml, coding_contract_data, tmp_path: Path) -> None:
        contract = load_contract(tmp_yaml(coding_contract_data))
        enforcer = ContractEnforcer(contract, repo_root=tmp_path)
        enforcer.record_check("pytest", "pass", exit_code=0)
        enforcer.record_check("ruff", "pass", exit_code=0)
        verdict = enforcer.finalize_run(output={"status": "done"})
        assert verdict.outcome == "pass"
        verdict_path = Path(verdict.artifacts["verdict_path"])
        assert verdict_path.exists()
        payload = json.loads(verdict_path.read_text(encoding="utf-8"))
        assert payload["final_gate"] == "allowed"
        assert payload["budgets"]["shell_commands"] == 0

    def test_cost_budget(self, enforcer_tier1) -> None:
        enforcer_tier1.add_cost(0.30)
        enforcer_tier1.add_cost(0.15)
        with pytest.raises(ContractViolation, match="cost_usd"):
            enforcer_tier1.add_cost(0.10)

    def test_token_budget(self, tmp_yaml, tier1_data) -> None:
        tier1_data["resources"]["budgets"]["max_tokens"] = 1000
        enforcer = ContractEnforcer(load_contract(tmp_yaml(tier1_data)), violation_destination="callback", violation_callback=lambda e: None)
        enforcer.add_tokens(800)
        with pytest.raises(ContractViolation, match="tokens"):
            enforcer.add_tokens(300)

    def test_input_validation(self, enforcer_tier1) -> None:
        assert enforcer_tier1.validate_input({"query": "hello"}) == []

    def test_input_validation_failure(self, enforcer_tier1) -> None:
        assert enforcer_tier1.validate_input({"query": 123})

    def test_output_validation(self, enforcer_tier1) -> None:
        assert enforcer_tier1.validate_output({"result": "answer"}) == []

    def test_violations_accumulated(self, tmp_yaml, tier1_data) -> None:
        contract = load_contract(tmp_yaml(tier1_data))
        events = []
        enforcer = ContractEnforcer(contract, violation_destination="callback", violation_callback=lambda e: events.append(e))
        with pytest.raises(ContractViolation):
            enforcer.check_tool_call("unauthorized_tool")
        assert len(enforcer.violations) == 1
        assert len(events) == 1

    def test_context_manager_finalizes(self, tmp_yaml, coding_contract_data, tmp_path: Path) -> None:
        contract = load_contract(tmp_yaml(coding_contract_data))
        with ContractEnforcer(contract, repo_root=tmp_path) as enforcer:
            enforcer.record_check("pytest", "pass", exit_code=0)
            enforcer.record_check("ruff", "pass", exit_code=0)
            enforcer.finalize_run(output={"status": "done"})
        assert enforcer.artifact_path is not None
        assert enforcer.artifact_path.exists()

    def test_no_effects_allows_all(self, tmp_yaml, tier0_data) -> None:
        enforcer = ContractEnforcer(load_contract(tmp_yaml(tier0_data)), violation_destination="callback", violation_callback=lambda e: None)
        enforcer.check_tool_call("anything")


class TestEnforceContractDecorator:
    def test_decorator_basic(self, tmp_yaml, tier0_data) -> None:
        path = tmp_yaml(tier0_data)

        @enforce_contract(str(path), violation_destination="callback")
        def my_agent(query: str, _enforcer: Any = None) -> str:
            return "result"

        assert my_agent("hello") == "result"

    def test_decorator_postcondition_fail(self, tmp_yaml) -> None:
        data = {
            "agent_contract": "0.1.0",
            "identity": {"name": "strict-agent", "version": "1.0.0"},
            "contract": {
                "postconditions": [
                    {"name": "not_none", "check": "output is not None", "enforcement": "sync_block"}
                ]
            },
        }
        path = tmp_yaml(data)

        @enforce_contract(str(path), violation_destination="callback")
        def bad_agent(query: str, _enforcer: Any = None) -> None:
            return None

        with pytest.raises(PostconditionError):
            bad_agent("hello")
