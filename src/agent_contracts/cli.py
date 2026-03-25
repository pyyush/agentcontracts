"""CLI for Agent Contracts — validate, check-compat, init, test."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from agent_contracts._version import __version__


@click.group()
@click.version_option(version=__version__, prog_name="agent-contracts")
def main() -> None:
    """Agent Contracts — YAML spec + SDK for production agent reliability."""
    pass


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON.")
def validate(contract_path: str, json_output: bool) -> None:
    """Validate a contract YAML file against the spec."""
    from agent_contracts.loader import (
        ContractLoadError,
        load_contract_yaml,
        validate_contract,
    )
    from agent_contracts.tier import assess_tier, recommend_upgrades

    try:
        data = load_contract_yaml(contract_path)
    except ContractLoadError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    errors = validate_contract(data)
    tier = assess_tier(data)
    recommendations = recommend_upgrades(data, tier)

    tier_names = {0: "Standalone", 1: "Enforceable", 2: "Composable"}

    if json_output:
        result = {
            "valid": len(errors) == 0,
            "tier": tier,
            "tier_name": tier_names.get(tier, "Unknown"),
            "errors": errors,
            "recommendations": [
                {"field": r.field, "target_tier": r.target_tier, "reason": r.reason}
                for r in recommendations
            ],
        }
        click.echo(json.dumps(result, indent=2))
    else:
        identity = data.get("identity", {})
        name = identity.get("name", "unknown")
        version = identity.get("version", "?")

        click.echo(f"Contract: {name}@{version}")
        click.echo(f"Spec version: {data.get('agent_contract', '?')}")

        if errors:
            click.echo(f"\nValidation: FAILED ({len(errors)} error(s))")
            for e in errors:
                click.echo(f"  - {e}")
            sys.exit(1)
        else:
            click.echo("\nValidation: PASSED")

        click.echo(f"Tier: {tier} ({tier_names.get(tier, 'Unknown')})")

        if recommendations:
            click.echo(f"\nRecommendations to reach Tier {tier + 1}:")
            for r in recommendations:
                click.echo(f"  + {r.field}: {r.reason}")

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
    except ContractLoadError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    report = check_compatibility(producer, consumer)

    if json_output:
        result = {
            "compatible": report.compatible,
            "producer": report.producer,
            "consumer": report.consumer,
            "schema_gaps": [{"field": g.field_path, "issue": g.issue} for g in report.schema_gaps],
            "capability_gaps": [{"tool": g.tool, "reason": g.reason} for g in report.capability_gaps],
            "budget_gaps": [
                {"type": g.budget_type, "producer_limit": g.producer_limit,
                 "consumer_limit": g.consumer_limit, "issue": g.issue}
                for g in report.budget_gaps
            ],
            "effect_violations": report.effect_violations,
            "warnings": report.warnings,
        }
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(report.summary())

        if report.schema_gaps:
            click.echo("\nSchema gaps:")
            for g in report.schema_gaps:
                click.echo(f"  - {g.field_path}: {g.issue}")

        if report.capability_gaps:
            click.echo("\nCapability gaps:")
            for g in report.capability_gaps:
                click.echo(f"  - {g.tool}: {g.reason}")

        if report.budget_gaps:
            click.echo("\nBudget gaps:")
            for g in report.budget_gaps:
                click.echo(f"  - {g.issue}")

        if report.effect_violations:
            click.echo("\nEffect violations:")
            for v in report.effect_violations:
                click.echo(f"  - {v}")

        if report.warnings:
            click.echo("\nWarnings:")
            for w in report.warnings:
                click.echo(f"  - {w}")

    if not report.compatible:
        sys.exit(1)


@main.command()
@click.option("--from-trace", "-t", "trace_path", type=click.Path(exists=True),
              help="JSONL trace file to generate from.")
@click.option("--name", "-n", "agent_name", help="Agent name override.")
@click.option("--version", "-v", "agent_version", help="Agent version override.")
@click.option("--output", "-o", "output_path", type=click.Path(), help="Output file path.")
def init(trace_path: Optional[str], agent_name: Optional[str], agent_version: Optional[str],
         output_path: Optional[str]) -> None:
    """Generate a contract skeleton (optionally from execution traces)."""
    from agent_contracts.init_from_trace import generate_contract_yaml

    if trace_path:
        result = generate_contract_yaml(
            trace_path, agent_name=agent_name, agent_version=agent_version
        )
    else:
        # Generate a minimal template
        template = {
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
                        "enforcement": "sync_block",
                        "severity": "critical",
                    }
                ]
            },
        }
        result = yaml.dump(template, sort_keys=False, default_flow_style=False)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")
        click.echo(f"Contract written to {output_path}")
    else:
        click.echo(result)


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option("--eval-suite", "-e", "eval_dir", type=click.Path(exists=True),
              help="Directory containing eval test cases (JSONL).")
def test(contract_path: str, eval_dir: Optional[str]) -> None:
    """Run eval suite against contract postconditions."""
    from agent_contracts.loader import ContractLoadError, load_contract
    from agent_contracts.postconditions import PostconditionError, evaluate_postconditions

    try:
        contract = load_contract(contract_path)
    except ContractLoadError as e:
        click.echo(f"Error loading contract: {e}", err=True)
        sys.exit(1)

    if not eval_dir:
        click.echo(f"Contract '{contract.identity.name}' loaded (Tier {contract.tier}).")
        click.echo(f"Postconditions: {len(contract.postconditions)}")
        for pc in contract.postconditions:
            click.echo(f"  - {pc.name} ({pc.enforcement}): {pc.check}")
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

    for tf in test_files:
        click.echo(f"\n--- {tf.name} ---")
        with open(tf, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
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
                    results = evaluate_postconditions(
                        contract.postconditions, output
                    )
                    all_passed = all(r.passed for r in results)
                    if all_passed:
                        passed += 1
                        click.echo(f"  Case {line_num}: PASS")
                    else:
                        failed += 1
                        failed_names = [r.postcondition.name for r in results if not r.passed]
                        click.echo(f"  Case {line_num}: FAIL ({', '.join(failed_names)})")
                except PostconditionError as e:
                    failed += 1
                    click.echo(f"  Case {line_num}: FAIL (blocked: {e.postcondition.name})")

    click.echo(f"\nResults: {passed}/{total} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
