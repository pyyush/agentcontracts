"""Local smoke tests for the release workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "publish.yml"


@pytest.fixture(scope="module")
def workflow_definition() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _publish_step_with_name(workflow_definition: dict[str, Any], name: str) -> dict[str, Any]:
    publish_steps = workflow_definition["jobs"]["publish"]["steps"]
    return next(step for step in publish_steps if step.get("name") == name)


def test_publish_workflow_marks_pep440_prerelease_tags(
    workflow_definition: dict[str, Any]
) -> None:
    detect_step = _publish_step_with_name(workflow_definition, "Detect release type")
    release_step = _publish_step_with_name(workflow_definition, "Create GitHub Release")
    detect_script = detect_step["run"]

    assert detect_step["id"] == "release_type"
    assert "set -euo pipefail" in detect_script
    assert 'VERSION="${GITHUB_REF_NAME#v}"' in detect_script
    assert '"$VERSION" == *a*' in detect_script
    assert '"$VERSION" == *b*' in detect_script
    assert '"$VERSION" == *rc*' in detect_script
    assert '"$VERSION" == *.dev*' in detect_script
    assert 'echo "prerelease=$prerelease" >> "$GITHUB_OUTPUT"' in detect_script
    assert release_step["with"]["generate_release_notes"] is True
    assert release_step["with"]["prerelease"] == "${{ steps.release_type.outputs.prerelease }}"
