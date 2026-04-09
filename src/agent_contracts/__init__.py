"""Agent Contracts — repo-local contracts for coding/build agents.

Quick start:
    from agent_contracts import load_contract, ContractEnforcer

    contract = load_contract("AGENT_CONTRACT.yaml")
    with ContractEnforcer(contract) as enforcer:
        enforcer.check_tool_call("search")
        enforcer.check_file_write("src/app.py")
        enforcer.check_shell_command("python -m pytest tests/")
        enforcer.evaluate_postconditions(result)
        enforcer.finalize_run(output=result)
"""

from agent_contracts._version import __version__
from agent_contracts.budgets import BudgetExceededError, BudgetTracker
from agent_contracts.composition import CompatibilityReport, check_compatibility
from agent_contracts.effects import EffectDeniedError, EffectGuard
from agent_contracts.enforcer import (
    ContractEnforcer,
    ContractViolation,
    RunCheckResult,
    RunVerdict,
    enforce_contract,
)
from agent_contracts.loader import ContractLoadError, load_contract, validate_contract
from agent_contracts.postconditions import PostconditionError, PreconditionError
from agent_contracts.tier import TierRecommendation, assess_tier, recommend_upgrades
from agent_contracts.types import (
    Contract,
    ContractIdentity,
    DelegationRules,
    EffectsAuthorized,
    EffectsDeclared,
    FailureModel,
    FilesystemAuthorization,
    ObservabilityConfig,
    PostconditionDef,
    PreconditionDef,
    ResourceBudgets,
    ShellAuthorization,
    SLOConfig,
    VersioningConfig,
)
from agent_contracts.violations import ViolationEmitter, ViolationEvent

__all__ = [
    "__version__",
    "Contract",
    "ContractIdentity",
    "PostconditionDef",
    "PreconditionDef",
    "EffectsAuthorized",
    "EffectsDeclared",
    "FilesystemAuthorization",
    "ShellAuthorization",
    "ResourceBudgets",
    "DelegationRules",
    "FailureModel",
    "ObservabilityConfig",
    "VersioningConfig",
    "SLOConfig",
    "load_contract",
    "validate_contract",
    "ContractLoadError",
    "assess_tier",
    "recommend_upgrades",
    "TierRecommendation",
    "ContractEnforcer",
    "ContractViolation",
    "RunCheckResult",
    "RunVerdict",
    "enforce_contract",
    "EffectGuard",
    "EffectDeniedError",
    "BudgetTracker",
    "BudgetExceededError",
    "PostconditionError",
    "PreconditionError",
    "ViolationEvent",
    "ViolationEmitter",
    "check_compatibility",
    "CompatibilityReport",
]
