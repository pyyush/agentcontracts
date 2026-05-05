"""Shared helpers for runnable Agent Contracts examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from agent_contracts import ContractEnforcer, RunVerdict

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACT_DIR = EXAMPLES_DIR / ".demo-artifacts"


def parse_artifact_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--artifact-dir",
        default=str(DEFAULT_ARTIFACT_DIR),
        help="Directory where the demo verdict artifact should be written.",
    )
    return parser.parse_args()


def artifact_path(raw_dir: str, filename: str) -> Path:
    directory = Path(raw_dir)
    if not directory.is_absolute():
        directory = REPO_ROOT / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename


def demo_enforcer(contract_path: Path, host_name: str, run_id: str) -> ContractEnforcer:
    from agent_contracts import load_contract

    contract = load_contract(contract_path)
    return ContractEnforcer(
        contract,
        repo_root=REPO_ROOT,
        host_name=host_name,
        host_version="demo",
        run_id=run_id,
        violation_destination="callback",
        violation_callback=lambda event: None,
    )


def summarize_verdict(verdict: RunVerdict) -> Dict[str, Any]:
    violations: List[str] = [
        str(violation.get("violated_clause")) for violation in verdict.to_dict()["violations"]
    ]
    checks: List[str] = [f"{check.name}:{check.status}" for check in verdict.checks]
    return {
        "outcome": verdict.outcome,
        "final_gate": verdict.final_gate,
        "artifact_path": verdict.artifacts["verdict_path"],
        "violations": violations,
        "checks": checks,
    }


def print_verdict_summary(verdict: RunVerdict) -> None:
    print(json.dumps(summarize_verdict(verdict), indent=2, sort_keys=True))
