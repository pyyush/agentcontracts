"""Tests that the documented runnable examples stay runnable."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agent_contracts.schema import validate_verdict_against_schema

ROOT = Path(__file__).resolve().parents[1]


def test_runnable_examples_emit_expected_verdicts(tmp_path: Path) -> None:
    demos = [
        ("run_green_pass.py", "pass", "allowed"),
        ("run_blocked_file_write.py", "blocked", "blocked"),
        ("run_blocked_command.py", "blocked", "blocked"),
        ("run_failed_checks.py", "fail", "failed"),
    ]

    for script_name, expected_outcome, expected_gate in demos:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "examples" / script_name),
                "--artifact-dir",
                str(tmp_path),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        summary = json.loads(result.stdout)
        verdict_path = Path(summary["artifact_path"])
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))

        assert summary["outcome"] == expected_outcome
        assert summary["final_gate"] == expected_gate
        assert verdict["outcome"] == expected_outcome
        assert verdict["final_gate"] == expected_gate
        assert validate_verdict_against_schema(verdict) == []


def test_committed_sample_verdicts_validate() -> None:
    verdict_paths = sorted((ROOT / "examples" / "verdicts").glob("*.json"))
    assert len(verdict_paths) >= 3
    for verdict_path in verdict_paths:
        payload = json.loads(verdict_path.read_text(encoding="utf-8"))
        assert validate_verdict_against_schema(payload) == []


def test_api_reference_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_api_reference.py"), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
