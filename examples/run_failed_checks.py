"""Failed-check demo: prove red repo checks produce a failing verdict."""

from __future__ import annotations

from _demo_helpers import (
    EXAMPLES_DIR,
    artifact_path,
    demo_enforcer,
    parse_artifact_args,
    print_verdict_summary,
)


def main() -> int:
    args = parse_artifact_args(__doc__ or "Agent Contracts failed-check demo.")
    with demo_enforcer(
        EXAMPLES_DIR / "demo_failed_checks.yaml",
        host_name="examples/run_failed_checks.py",
        run_id="example-failed-checks",
    ) as enforcer:
        enforcer.record_check(
            "pytest",
            "fail",
            exit_code=1,
            detail="demo simulates a red test suite",
            evidence={"command": "python -m pytest"},
        )
        enforcer.record_check(
            "ruff",
            "pass",
            exit_code=0,
            detail="demo simulates lint passing",
            evidence={"command": "python -m ruff check src/ tests/"},
        )
        verdict = enforcer.finalize_run(
            output={"status": "done"},
            artifact_path=artifact_path(args.artifact_dir, "failed-checks.json"),
        )

    print_verdict_summary(verdict)
    return 0 if verdict.outcome == "fail" and verdict.final_gate == "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
