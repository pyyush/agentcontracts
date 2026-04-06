"""Contract loading — parse YAML, validate schema, build typed Contract objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from agent_contracts.schema import validate_against_schema
from agent_contracts.tier import assess_tier
from agent_contracts.types import (
    CircuitBreakerConfig,
    Contract,
    ContractIdentity,
    ContractSatisfactionSLO,
    CostSLO,
    DelegationRules,
    EffectsAuthorized,
    EffectsDeclared,
    ErrorDef,
    FailureModel,
    FilesystemAuthorization,
    LatencySLO,
    MetricDef,
    ObservabilityConfig,
    PostconditionDef,
    PostconditionSLO,
    PreconditionDef,
    ResourceBudgets,
    ShellAuthorization,
    SLOConfig,
    SubstitutionConfig,
    TracesConfig,
    VersioningConfig,
    ViolationEventsConfig,
)


class ContractLoadError(Exception):
    """Raised when a contract cannot be loaded or validated."""

    def __init__(self, message: str, errors: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def load_contract_yaml(source: Union[str, Path]) -> Dict[str, Any]:
    """Load a YAML file and return the parsed dict.

    Raises ContractLoadError on parse failure.
    """
    path = Path(source)
    if not path.exists():
        raise ContractLoadError(f"Contract file not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ContractLoadError(f"YAML parse error: {e}") from e

    if not isinstance(data, dict):
        raise ContractLoadError("Contract must be a YAML mapping (object), not a scalar or list.")
    return data


def validate_contract(data: Dict[str, Any]) -> List[str]:
    """Validate parsed YAML against the JSON Schema. Returns error messages."""
    return validate_against_schema(data)


def _build_postcondition(raw: Dict[str, Any]) -> PostconditionDef:
    slo_raw = raw.get("slo")
    slo = PostconditionSLO(**slo_raw) if isinstance(slo_raw, dict) else None
    return PostconditionDef(
        name=raw["name"],
        check=raw["check"],
        enforcement=raw.get("enforcement", "sync_warn"),
        severity=raw.get("severity", "major"),
        description=raw.get("description"),
        slo=slo,
    )


def _build_effects_authorized(raw: Dict[str, Any]) -> EffectsAuthorized:
    filesystem_raw = raw.get("filesystem")
    filesystem = None
    if isinstance(filesystem_raw, dict):
        filesystem = FilesystemAuthorization(
            read=filesystem_raw.get("read", []),
            write=filesystem_raw.get("write", []),
        )

    shell_raw = raw.get("shell")
    shell = None
    if isinstance(shell_raw, dict):
        shell = ShellAuthorization(commands=shell_raw.get("commands", []))

    return EffectsAuthorized(
        tools=raw.get("tools", []),
        network=raw.get("network", []),
        state_writes=raw.get("state_writes", []),
        filesystem=filesystem,
        shell=shell,
    )


def _build_effects_declared(raw: Dict[str, Any]) -> EffectsDeclared:
    return EffectsDeclared(
        tools=raw.get("tools", []),
        network=raw.get("network", []),
        state_writes=raw.get("state_writes", []),
    )


def _build_budgets(raw: Dict[str, Any]) -> ResourceBudgets:
    budgets = raw.get("budgets", raw)
    return ResourceBudgets(
        max_cost_usd=budgets.get("max_cost_usd"),
        max_tokens=budgets.get("max_tokens"),
        max_tool_calls=budgets.get("max_tool_calls"),
        max_duration_seconds=budgets.get("max_duration_seconds"),
        max_shell_commands=budgets.get("max_shell_commands"),
    )


def _build_failure_model(raw: Dict[str, Any]) -> FailureModel:
    errors = [
        ErrorDef(
            name=e["name"],
            retryable=e.get("retryable", False),
            max_retries=e.get("max_retries", 0),
            fallback=e.get("fallback"),
            description=e.get("description"),
        )
        for e in raw.get("errors", [])
    ]
    cb_raw = raw.get("circuit_breaker")
    cb = CircuitBreakerConfig(**cb_raw) if isinstance(cb_raw, dict) else None
    return FailureModel(
        errors=errors,
        default_timeout_seconds=raw.get("default_timeout_seconds"),
        circuit_breaker=cb,
    )


def _build_delegation(raw: Dict[str, Any]) -> DelegationRules:
    return DelegationRules(
        max_depth=raw.get("max_depth", 3),
        attenuate_effects=raw.get("attenuate_effects", True),
        require_contract=raw.get("require_contract", False),
        allowed_agents=raw.get("allowed_agents"),
    )


def _build_observability(raw: Dict[str, Any]) -> ObservabilityConfig:
    traces_raw = raw.get("traces")
    traces = TracesConfig(**traces_raw) if isinstance(traces_raw, dict) else None
    metrics = [
        MetricDef(
            name=m["name"],
            type=m["type"],
            description=m.get("description"),
        )
        for m in raw.get("metrics", [])
    ]
    ve_raw = raw.get("violation_events")
    ve = ViolationEventsConfig(**ve_raw) if isinstance(ve_raw, dict) else None
    return ObservabilityConfig(
        traces=traces,
        metrics=metrics,
        violation_events=ve,
        run_artifact_path=raw.get("run_artifact_path"),
    )


def _build_versioning(raw: Dict[str, Any]) -> VersioningConfig:
    sub_raw = raw.get("substitution")
    sub = SubstitutionConfig(**sub_raw) if isinstance(sub_raw, dict) else None
    return VersioningConfig(
        build_id=raw.get("build_id"),
        breaking_changes=raw.get("breaking_changes", []),
        substitution=sub,
    )


def _build_slo(raw: Dict[str, Any]) -> SLOConfig:
    csr_raw = raw.get("contract_satisfaction_rate")
    csr = ContractSatisfactionSLO(**csr_raw) if isinstance(csr_raw, dict) else None
    lat_raw = raw.get("latency")
    lat = LatencySLO(**lat_raw) if isinstance(lat_raw, dict) else None
    cost_raw = raw.get("cost")
    cost = CostSLO(**cost_raw) if isinstance(cost_raw, dict) else None
    return SLOConfig(
        contract_satisfaction_rate=csr,
        latency=lat,
        cost=cost,
        error_budget_policy=raw.get("error_budget_policy"),
    )


def load_contract(source: Union[str, Path], *, strict: bool = True) -> Contract:
    """Load, validate, and build a Contract from a YAML file.

    Args:
        source: Path to the AGENT_CONTRACT.yaml file.
        strict: If True, raise ContractLoadError on schema violations.

    Returns:
        A fully constructed Contract object.

    Raises:
        ContractLoadError: If the file cannot be loaded or fails validation.
    """
    data = load_contract_yaml(source)
    errors = validate_contract(data)
    if errors and strict:
        raise ContractLoadError(
            f"Contract validation failed with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors),
            errors=errors,
        )

    tier = assess_tier(data)

    identity_raw = data.get("identity", {})
    identity = ContractIdentity(
        name=identity_raw.get("name", ""),
        version=identity_raw.get("version", ""),
        description=identity_raw.get("description"),
        authors=identity_raw.get("authors"),
    )

    contract_raw = data.get("contract", {})
    postconditions = [_build_postcondition(p) for p in contract_raw.get("postconditions", [])]

    inputs_raw = data.get("inputs")
    input_schema = inputs_raw.get("schema") if isinstance(inputs_raw, dict) else None
    preconditions = None
    if isinstance(inputs_raw, dict) and "preconditions" in inputs_raw:
        preconditions = [
            PreconditionDef(
                name=p["name"],
                check=p["check"],
                description=p.get("description"),
            )
            for p in inputs_raw["preconditions"]
        ]

    outputs_raw = data.get("outputs")
    output_schema = outputs_raw.get("schema") if isinstance(outputs_raw, dict) else None

    effects_raw = data.get("effects")
    effects_authorized = None
    effects_declared = None
    if isinstance(effects_raw, dict):
        if "authorized" in effects_raw:
            effects_authorized = _build_effects_authorized(effects_raw["authorized"])
        if "declared" in effects_raw:
            effects_declared = _build_effects_declared(effects_raw["declared"])

    resources_raw = data.get("resources")
    budgets = _build_budgets(resources_raw) if isinstance(resources_raw, dict) else None

    fm_raw = data.get("failure_model")
    failure_model = _build_failure_model(fm_raw) if isinstance(fm_raw, dict) else None

    del_raw = data.get("delegation")
    delegation = _build_delegation(del_raw) if isinstance(del_raw, dict) else None

    obs_raw = data.get("observability")
    observability = _build_observability(obs_raw) if isinstance(obs_raw, dict) else None

    ver_raw = data.get("versioning")
    versioning = _build_versioning(ver_raw) if isinstance(ver_raw, dict) else None

    slo_raw = data.get("slo")
    slo = _build_slo(slo_raw) if isinstance(slo_raw, dict) else None

    return Contract(
        spec_version=data.get("agent_contract", "0.1.0"),
        identity=identity,
        postconditions=postconditions,
        tier=tier,
        input_schema=input_schema,
        output_schema=output_schema,
        preconditions=preconditions,
        effects_authorized=effects_authorized,
        budgets=budgets,
        failure_model=failure_model,
        effects_declared=effects_declared,
        delegation=delegation,
        observability=observability,
        versioning=versioning,
        slo=slo,
        source_path=str(Path(source).resolve()),
        raw=data,
    )
