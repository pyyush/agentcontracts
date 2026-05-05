"""Local smoke tests for CI workflow guardrails."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

CI_WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def ci_workflow_definition() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))


def _test_step_with_name(ci_workflow_definition: dict[str, Any], name: str) -> dict[str, Any]:
    test_steps = ci_workflow_definition["jobs"]["test"]["steps"]
    return next(step for step in test_steps if step.get("name") == name)


def test_ci_hard_enforces_performance_budgets_only_on_representative_python(
    ci_workflow_definition: dict[str, Any]
) -> None:
    test_step = _test_step_with_name(ci_workflow_definition, "Test")

    assert test_step["env"]["AICONTRACTS_ENFORCE_PERF_BUDGETS"] == (
        "${{ matrix.python-version == '3.11' && 'true' || 'false' }}"
    )
