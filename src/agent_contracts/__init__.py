"""Agent Contracts — YAML spec + validation SDK for production agent reliability.

Quick start:
    from agent_contracts import load_contract, ContractEnforcer

    contract = load_contract("AGENT_CONTRACT.yaml")
    with ContractEnforcer(contract) as enforcer:
        enforcer.check_tool_call("search")
        enforcer.add_cost(0.05)
        enforcer.evaluate_postconditions(result)
"""

from agent_contracts._version import __version__
from agent_contracts.budgets import BudgetExceededError, BudgetTracker
from agent_contracts.composition import CompatibilityReport, check_compatibility
from agent_contracts.effects import EffectDeniedError, EffectGuard
from agent_contracts.enforcer import ContractEnforcer, ContractViolation, enforce_contract
from agent_contracts.loader import ContractLoadError, load_contract, validate_contract
from agent_contracts.postconditions import PostconditionError
from agent_contracts.tier import TierRecommendation, assess_tier, recommend_upgrades
from agent_contracts.types import (
    Contract,
    ContractIdentity,
    DelegationRules,
    EffectsAuthorized,
    EffectsDeclared,
    FailureModel,
    ObservabilityConfig,
    PostconditionDef,
    ResourceBudgets,
    SLOConfig,
    VersioningConfig,
)
from agent_contracts.violations import ViolationEmitter, ViolationEvent

__all__ = [
    "__version__",
    # Core types
    "Contract",
    "ContractIdentity",
    "PostconditionDef",
    "EffectsAuthorized",
    "EffectsDeclared",
    "ResourceBudgets",
    "DelegationRules",
    "FailureModel",
    "ObservabilityConfig",
    "VersioningConfig",
    "SLOConfig",
    # Loading
    "load_contract",
    "validate_contract",
    "ContractLoadError",
    # Tier
    "assess_tier",
    "recommend_upgrades",
    "TierRecommendation",
    # Enforcement
    "ContractEnforcer",
    "ContractViolation",
    "enforce_contract",
    # Effects
    "EffectGuard",
    "EffectDeniedError",
    # Budgets
    "BudgetTracker",
    "BudgetExceededError",
    # Postconditions
    "PostconditionError",
    # Violations
    "ViolationEvent",
    "ViolationEmitter",
    # Composition
    "check_compatibility",
    "CompatibilityReport",
]
