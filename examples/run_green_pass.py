"""Green-path demo: emit a passing verdict artifact for a bounded repo run."""

from __future__ import annotations

from _demo_helpers import (
    EXAMPLES_DIR,
    artifact_path,
    demo_enforcer,
    parse_artifact_args,
    print_verdict_summary,
)


def main() -> int:
    args = parse_artifact_args(__doc__ or "Agent Contracts green-path demo.")
    with demo_enforcer(
        EXAMPLES_DIR / "repo_build_agent.yaml",
        host_name="examples/run_green_pass.py",
        run_id="example-green-pass",
    ) as enforcer:
        enforcer.check_file_read("README.md")
        enforcer.check_file_write("src/example_patch.py")
        enforcer.check_shell_command("python -m pytest tests/test_cli.py")
        enforcer.record_check(
            "pytest",
            "pass",
            exit_code=0,
            detail="demo records the required repo check as passing",
            evidence={"command": "python -m pytest tests/test_cli.py"},
        )
        enforcer.record_check(
            "ruff",
            "pass",
            exit_code=0,
            detail="demo records lint as passing",
            evidence={"command": "python -m ruff check src/ tests/"},
        )
        verdict = enforcer.finalize_run(
            output={"status": "done"},
            artifact_path=artifact_path(args.artifact_dir, "green-pass.json"),
        )

    print_verdict_summary(verdict)
    return 0 if verdict.outcome == "pass" and verdict.final_gate == "allowed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
