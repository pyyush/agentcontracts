"""Blocked file demo: prove a protected write fails closed with a verdict."""

from __future__ import annotations

from _demo_helpers import (
    EXAMPLES_DIR,
    artifact_path,
    demo_enforcer,
    parse_artifact_args,
    print_verdict_summary,
)

from agent_contracts import ContractViolation


def main() -> int:
    args = parse_artifact_args(__doc__ or "Agent Contracts blocked-file demo.")
    with demo_enforcer(
        EXAMPLES_DIR / "demo_blocked_file_write.yaml",
        host_name="examples/run_blocked_file_write.py",
        run_id="example-blocked-file-write",
    ) as enforcer:
        error = None
        try:
            enforcer.check_file_write("tests/secret.env")
        except ContractViolation as exc:
            error = exc
        verdict = enforcer.finalize_run(
            execution_error=error,
            artifact_path=artifact_path(args.artifact_dir, "blocked-file-write.json"),
        )

    print_verdict_summary(verdict)
    return 0 if verdict.outcome == "blocked" and error is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
