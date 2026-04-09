"""CLI for Agent Contracts — repo-local guardrails for coding/build agents."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from agent_contracts._version import __version__
from agent_contracts.enforcer import load_verdict_artifact


@click.group()
@click.version_option(version=__version__, prog_name="aicontracts")
def main() -> None:
    """Agent Contracts — repo-local fail-closed guardrails for coding/build agents."""
    pass


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON.")
def validate(contract_path: str, json_output: bool) -> None:
    """Validate a contract YAML file against the spec."""
    from agent_contracts.loader import ContractLoadError, load_contract_yaml, validate_contract
    from agent_contracts.tier import assess_tier, recommend_upgrades

    try:
        data = load_contract_yaml(contract_path)
    except ContractLoadError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    errors = validate_contract(data)
    tier = assess_tier(data)
    recommendations = recommend_upgrades(data, tier)
    tier_names = {0: "Standalone", 1: "Enforceable", 2: "Composable"}

    authorized = data.get("effects", {}).get("authorized", {})
    filesystem = authorized.get("filesystem", {}) if isinstance(authorized, dict) else {}
    shell = authorized.get("shell", {}) if isinstance(authorized, dict) else {}
    observability = data.get("observability", {})

    if json_output:
        result = {
            "valid": len(errors) == 0,
            "tier": tier,
            "tier_name": tier_names.get(tier, "Unknown"),
            "errors": errors,
            "recommendations": [
                {
                    "field": item.field,
                    "target_tier": item.target_tier,
                    "reason": item.reason,
                }
                for item in recommendations
            ],
            "coding_surfaces": {
                "filesystem_read": filesystem.get("read", []),
                "filesystem_write": filesystem.get("write", []),
                "shell_commands": shell.get("commands", []),
                "run_artifact_path": observability.get("run_artifact_path"),
            },
        }
        click.echo(json.dumps(result, indent=2))
    else:
        identity = data.get("identity", {})
        click.echo(f"Contract: {identity.get('name', 'unknown')}@{identity.get('version', '?')}")
        click.echo(f"Spec version: {data.get('agent_contract', '?')}")
        if errors:
            click.echo(f"\nValidation: FAILED ({len(errors)} error(s))")
            for error in errors:
                click.echo(f"  - {error}")
            sys.exit(1)
        click.echo("\nValidation: PASSED")
        click.echo(f"Tier: {tier} ({tier_names.get(tier, 'Unknown')})")
        if filesystem or shell or observability.get("run_artifact_path"):
            click.echo("\nCoding/build surfaces:")
            if filesystem:
                click.echo(f"  read:  {filesystem.get('read', [])}")
                click.echo(f"  write: {filesystem.get('write', [])}")
            if shell:
                click.echo(f"  shell: {shell.get('commands', [])}")
            if observability.get("run_artifact_path"):
                click.echo(f"  verdict artifact: {observability['run_artifact_path']}")
        if recommendations:
            click.echo(f"\nRecommendations to reach Tier {tier + 1}:")
            for item in recommendations:
                click.echo(f"  + {item.field}: {item.reason}")

    if errors:
        sys.exit(1)


@main.command("check-compat")
@click.argument("producer_path", type=click.Path(exists=True))
@click.argument("consumer_path", type=click.Path(exists=True))
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON.")
def check_compat(producer_path: str, consumer_path: str, json_output: bool) -> None:
    """Check composition compatibility between two contracts."""
    from agent_contracts.composition import check_compatibility
    from agent_contracts.loader import ContractLoadError, load_contract

    try:
        producer = load_contract(producer_path)
        consumer = load_contract(consumer_path)
    except ContractLoadError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    report = check_compatibility(producer, consumer)
    if json_output:
        result = {
            "compatible": report.compatible,
            "producer": report.producer,
            "consumer": report.consumer,
            "schema_gaps": [
                {"field": gap.field_path, "issue": gap.issue} for gap in report.schema_gaps
            ],
            "capability_gaps": [
                {"tool": gap.tool, "reason": gap.reason} for gap in report.capability_gaps
            ],
            "budget_gaps": [
                {
                    "type": gap.budget_type,
                    "producer_limit": gap.producer_limit,
                    "consumer_limit": gap.consumer_limit,
                    "issue": gap.issue,
                }
                for gap in report.budget_gaps
            ],
            "effect_violations": report.effect_violations,
            "warnings": report.warnings,
        }
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(report.summary())
        if report.schema_gaps:
            click.echo("\nSchema gaps:")
            for gap in report.schema_gaps:
                click.echo(f"  - {gap.field_path}: {gap.issue}")
        if report.capability_gaps:
            click.echo("\nCapability gaps:")
            for capability_gap in report.capability_gaps:
                click.echo(f"  - {capability_gap.tool}: {capability_gap.reason}")
        if report.budget_gaps:
            click.echo("\nBudget gaps:")
            for budget_gap in report.budget_gaps:
                click.echo(f"  - {budget_gap.issue}")
        if report.effect_violations:
            click.echo("\nEffect violations:")
            for violation in report.effect_violations:
                click.echo(f"  - {violation}")
        if report.warnings:
            click.echo("\nWarnings:")
            for warning in report.warnings:
                click.echo(f"  - {warning}")

    if not report.compatible:
        sys.exit(1)


@main.command()
@click.option("--from-trace", "-t", "trace_path", type=click.Path(exists=True), help="JSONL trace file to generate from.")
@click.option("--name", "-n", "agent_name", help="Agent name override.")
@click.option("--version", "-v", "agent_version", help="Agent version override.")
@click.option("--output", "-o", "output_path", type=click.Path(), help="Output file path.")
@click.option(
    "--template",
    type=click.Choice(["basic", "coding"], case_sensitive=False),
    default="basic",
    show_default=True,
    help="Template to use when not generating from traces.",
)
def init(
    trace_path: Optional[str],
    agent_name: Optional[str],
    agent_version: Optional[str],
    output_path: Optional[str],
    template: str,
) -> None:
    """Generate a contract skeleton (optionally from execution traces)."""
    from agent_contracts.init_from_trace import generate_contract_yaml

    if trace_path:
        result = generate_contract_yaml(
            trace_path, agent_name=agent_name, agent_version=agent_version
        )
    else:
        if template == "coding":
            payload = {
                "agent_contract": "0.1.0",
                "identity": {
                    "name": agent_name or "repo-build-agent",
                    "version": agent_version or "0.1.0",
                    "description": "Repo-local coding/build agent with fail-closed scopes.",
                },
                "effects": {
                    "authorized": {
                        "filesystem": {
                            "read": ["src/**", "tests/**", "README.md", "pyproject.toml"],
                            "write": ["src/**", "tests/**", "README.md"],
                        },
                        "shell": {
                            "commands": [
                                "python -m pytest *",
                                "python -m ruff check *",
                            ]
                        },
                        "tools": [],
                        "network": [],
                        "state_writes": [],
                    }
                },
                "resources": {
                    "budgets": {
                        "max_tokens": 50000,
                        "max_tool_calls": 20,
                        "max_shell_commands": 10,
                        "max_duration_seconds": 1800,
                    }
                },
                "observability": {
                    "run_artifact_path": ".agent-contracts/runs/{run_id}/verdict.json"
                },
                "contract": {
                    "postconditions": [
                        {
                            "name": "repo_checks_green",
                            "check": "checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0",
                        }
                    ]
                },
            }
        else:
            payload = {
                "agent_contract": "0.1.0",
                "identity": {
                    "name": agent_name or "my-agent",
                    "version": agent_version or "0.1.0",
                    "description": "TODO: Describe what this agent does.",
                },
                "contract": {
                    "postconditions": [
                        {
                            "name": "produces_output",
                            "check": "output is not None",
                        }
                    ]
                },
            }
        result = yaml.dump(payload, sort_keys=False, default_flow_style=False)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")
        click.echo(f"Contract written to {output_path}")
    else:
        click.echo(result)


@main.command("check-verdict")
@click.argument("verdict_path", type=click.Path(exists=True))
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON.")
@click.option("--fail-on-warn", is_flag=True, help="Return non-zero for warn outcomes.")
def check_verdict(verdict_path: str, json_output: bool, fail_on_warn: bool) -> None:
    """Inspect a verdict artifact and return a CI-friendly exit code."""
    verdict = load_verdict_artifact(verdict_path)
    outcome = verdict.get("outcome", "unknown")
    final_gate = verdict.get("final_gate", "unknown")
    should_fail = outcome in {"blocked", "fail"} or (fail_on_warn and outcome == "warn")

    if json_output:
        click.echo(json.dumps(verdict, indent=2))
    else:
        click.echo(f"Outcome: {outcome}")
        click.echo(f"Final gate: {final_gate}")
        violations = verdict.get("violations", [])
        checks = verdict.get("checks", [])
        if violations:
            click.echo("\nViolations:")
            for violation in violations:
                click.echo(f"  - {violation.get('violated_clause')}")
        if checks:
            click.echo("\nChecks:")
            for check in checks:
                click.echo(f"  - {check.get('name')}: {check.get('status')}")

    if should_fail:
        sys.exit(1)


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option(
    "--eval-suite",
    "-e",
    "eval_dir",
    type=click.Path(exists=True),
    help="Directory containing eval test cases (JSONL).",
)
def test(contract_path: str, eval_dir: Optional[str]) -> None:
    """Run eval suite against contract postconditions."""
    from agent_contracts.loader import ContractLoadError, load_contract
    from agent_contracts.postconditions import PostconditionError, evaluate_postconditions

    try:
        contract = load_contract(contract_path)
    except ContractLoadError as exc:
        click.echo(f"Error loading contract: {exc}", err=True)
        sys.exit(1)

    if not eval_dir:
        click.echo(f"Contract '{contract.identity.name}' loaded (Tier {contract.tier}).")
        click.echo(f"Postconditions: {len(contract.postconditions)}")
        for postcondition in contract.postconditions:
            click.echo(
                f"  - {postcondition.name} ({postcondition.enforcement}): {postcondition.check}"
            )
        click.echo("\nNo eval suite specified. Use --eval-suite to run tests.")
        return

    eval_path = Path(eval_dir)
    test_files = sorted(eval_path.glob("*.jsonl"))
    if not test_files:
        click.echo(f"No .jsonl test files found in {eval_dir}", err=True)
        sys.exit(1)

    total = 0
    passed = 0
    failed = 0

    for test_file in test_files:
        click.echo(f"\n--- {test_file.name} ---")
        with open(test_file, encoding="utf-8") as handle:
            for line_num, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    case = json.loads(line)
                except json.JSONDecodeError:
                    click.echo(f"  Line {line_num}: SKIP (invalid JSON)")
                    continue
                output = case.get("output", case.get("result"))
                total += 1
                try:
                    results = evaluate_postconditions(contract.postconditions, output)
                    if all(result.passed for result in results):
                        passed += 1
                        click.echo(f"  Case {line_num}: PASS")
                    else:
                        failed += 1
                        failed_names = [
                            result.postcondition.name for result in results if not result.passed
                        ]
                        click.echo(f"  Case {line_num}: FAIL ({', '.join(failed_names)})")
                except PostconditionError as exc:
                    failed += 1
                    click.echo(
                        f"  Case {line_num}: FAIL (blocked: {exc.postcondition.name})"
                    )

    click.echo(f"\nResults: {passed}/{total} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
