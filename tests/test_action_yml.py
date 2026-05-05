"""Local smoke tests for the GitHub composite action."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ACTION_PATH = Path(__file__).resolve().parent.parent / "action.yml"


@pytest.fixture(scope="module")
def action_definition() -> dict[str, Any]:
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def _step_with_name(action_definition: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in action_definition["runs"]["steps"] if step.get("name") == name)


def test_action_defaults_to_published_pin_and_supports_release_install_override(
    action_definition: dict[str, Any]
) -> None:
    inputs = action_definition["inputs"]
    install_step = _step_with_name(action_definition, "Install aicontracts")
    install_script = install_step["run"]

    assert install_step["shell"] == "bash"
    assert inputs["package-spec"]["default"] == "aicontracts==0.2.0"
    assert inputs["allow-prerelease"]["default"] == "false"
    assert inputs["pip-index-url"]["default"] == ""
    assert inputs["pip-extra-index-url"]["default"] == ""
    assert install_step["env"]["AICONTRACTS_PACKAGE_SPEC"] == "${{ inputs.package-spec }}"
    assert install_step["env"]["AICONTRACTS_ALLOW_PRERELEASE"] == "${{ inputs.allow-prerelease }}"
    assert install_step["env"]["AICONTRACTS_PIP_INDEX_URL"] == "${{ inputs.pip-index-url }}"
    assert (
        install_step["env"]["AICONTRACTS_PIP_EXTRA_INDEX_URL"]
        == "${{ inputs.pip-extra-index-url }}"
    )
    assert "set -euo pipefail" in install_script
    assert 'if [ -z "$AICONTRACTS_PACKAGE_SPEC" ]; then' in install_script
    assert 'echo "::error::package-spec must not be empty"' in install_script
    assert 'if [ "$AICONTRACTS_ALLOW_PRERELEASE" = "true" ]; then' in install_script
    assert "pip_args+=(--pre)" in install_script
    assert 'elif [ "$AICONTRACTS_ALLOW_PRERELEASE" != "false" ]; then' in install_script
    assert 'pip_args+=(--index-url "$AICONTRACTS_PIP_INDEX_URL")' in install_script
    assert 'pip_args+=(--extra-index-url "$AICONTRACTS_PIP_EXTRA_INDEX_URL")' in install_script
    assert 'pip_args+=("$AICONTRACTS_PACKAGE_SPEC")' in install_script
    assert 'python -m pip "${pip_args[@]}"' in install_script


def test_action_maps_warning_inputs_to_gate_behavior(action_definition: dict[str, Any]) -> None:
    inputs = action_definition["inputs"]
    gate_step = _step_with_name(action_definition, "Validate contract and verdict")
    gate_script = gate_step["run"]

    assert inputs["fail-on-warning"]["default"] == "false"
    assert inputs["fail-on-warn-outcome"]["default"] == "false"
    assert 'if [ "${{ inputs.fail-on-warning }}" = "true" ] && [ "$recommendations" -gt 0 ]; then' in gate_script
    assert 'if [ "${{ inputs.fail-on-warn-outcome }}" = "true" ]; then' in gate_script
    assert 'extra_flag="--fail-on-warn"' in gate_script


def test_action_validates_contracts_and_fails_closed_on_verdict_gate(
    action_definition: dict[str, Any]
) -> None:
    gate_step = _step_with_name(action_definition, "Validate contract and verdict")
    gate_script = gate_step["run"]

    assert gate_step["shell"] == "bash"
    assert "set -euo pipefail" in gate_script
    assert 'result=$(python -m agent_contracts.cli validate "$contract" --json-output)' in gate_script
    assert 'if ! python -m agent_contracts.cli check-verdict "${{ inputs.verdict }}" $extra_flag; then' in gate_script
    assert 'outcome="fail"' in gate_script
    assert 'verdict_outcome=$(python -c \'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["outcome"])\' "${{ inputs.verdict }}")' in gate_script
    assert 'if [ "$outcome" = "fail" ]; then' in gate_script
    assert "exit 1" in gate_script
