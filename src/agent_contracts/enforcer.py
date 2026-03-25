"""Runtime enforcement middleware — the unified enforcement layer.

Wires together effects, budgets, postconditions, and violations into a
single enforcement flow. Supports three usage patterns:

1. Decorator: @enforce_contract("path/to/contract.yaml")
2. Context manager: with ContractEnforcer(contract) as enforcer: ...
3. Explicit API: enforcer.check_tool_call(name, args)
"""

from __future__ import annotations

import functools
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import jsonschema

from agent_contracts.budgets import BudgetExceededError, BudgetTracker
from agent_contracts.effects import EffectGuard
from agent_contracts.loader import load_contract
from agent_contracts.postconditions import (
    PostconditionResult,
    evaluate_postconditions,
)
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEmitter, ViolationEvent

F = TypeVar("F", bound=Callable[..., Any])


class ContractViolation(Exception):
    """Wraps any contract violation with context."""

    def __init__(self, message: str, event: Optional[ViolationEvent] = None) -> None:
        super().__init__(message)
        self.event = event


class ContractEnforcer:
    """Unified runtime enforcement for an agent contract.

    Enforces effects (default-deny), budgets (circuit breaker),
    input/output schema validation, and postconditions.
    """

    def __init__(
        self,
        contract: Contract,
        *,
        violation_destination: str = "stdout",
        violation_callback: Optional[Callable[[ViolationEvent], None]] = None,
        cost_callback: Optional[Callable[[], float]] = None,
    ) -> None:
        self._contract = contract
        self._effect_guard = EffectGuard(contract.effects_authorized)
        self._budget_tracker = BudgetTracker(contract.budgets, cost_callback=cost_callback)
        self._emitter = ViolationEmitter(
            destination=violation_destination, callback=violation_callback
        )
        self._warnings: List[str] = []

    @property
    def contract(self) -> Contract:
        return self._contract

    @property
    def budget_tracker(self) -> BudgetTracker:
        return self._budget_tracker

    @property
    def violations(self) -> List[ViolationEvent]:
        return self._emitter.events

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    # --- Input validation ---

    def validate_input(self, input_data: Any) -> List[str]:
        """Validate input against the contract's input schema.

        Returns list of validation errors. Raises ContractViolation
        if schema validation fails and enforcement is sync_block.
        """
        if self._contract.input_schema is None:
            return []
        validator = jsonschema.Draft202012Validator(self._contract.input_schema)
        errors = [e.message for e in validator.iter_errors(input_data)]
        if errors:
            self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause="inputs.schema",
                evidence={"errors": errors, "input_keys": list(input_data.keys()) if isinstance(input_data, dict) else str(type(input_data))},
                severity="major",
                enforcement="blocked",
            )
        return errors

    # --- Tool call interception ---

    def check_tool_call(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> None:
        """Check if a tool call is authorized and within budget.

        Raises ContractViolation if the tool is denied or budget exceeded.
        """
        # Effect check
        if not self._effect_guard.check_tool(tool_name):
            event = self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause="effects.authorized.tools",
                evidence={"tool": tool_name, "authorized": self._contract.effects_authorized.tools if self._contract.effects_authorized else []},
                severity="critical",
                enforcement="blocked",
            )
            raise ContractViolation(
                f"Tool '{tool_name}' not authorized by contract.", event=event
            )

        # Budget check — record the tool call
        try:
            self._budget_tracker.record_tool_call()
        except BudgetExceededError as e:
            event = self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause=f"resources.budgets.{e.budget_type}",
                evidence={"current": e.current, "limit": e.limit},
                severity="critical",
                enforcement="blocked",
            )
            raise ContractViolation(str(e), event=event) from e

    def add_cost(self, amount: float) -> None:
        """Record cost and check against budget limit."""
        try:
            self._budget_tracker.add_cost(amount)
        except BudgetExceededError as e:
            event = self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause="resources.budgets.max_cost_usd",
                evidence={"current": e.current, "limit": e.limit},
                severity="critical",
                enforcement="blocked",
            )
            raise ContractViolation(str(e), event=event) from e

    def add_tokens(self, count: int) -> None:
        """Record token usage and check against budget limit."""
        try:
            self._budget_tracker.add_tokens(count)
        except BudgetExceededError as e:
            event = self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause="resources.budgets.max_tokens",
                evidence={"current": e.current, "limit": e.limit},
                severity="critical",
                enforcement="blocked",
            )
            raise ContractViolation(str(e), event=event) from e

    # --- Output validation ---

    def validate_output(self, output_data: Any) -> List[str]:
        """Validate output against the contract's output schema."""
        if self._contract.output_schema is None:
            return []
        validator = jsonschema.Draft202012Validator(self._contract.output_schema)
        errors = [e.message for e in validator.iter_errors(output_data)]
        if errors:
            self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause="outputs.schema",
                evidence={"errors": errors},
                severity="major",
                enforcement="warned",
            )
        return errors

    # --- Postcondition evaluation ---

    def evaluate_postconditions(self, output: Any) -> List[PostconditionResult]:
        """Evaluate all postconditions against the output."""

        def on_warn(pc: Any, o: Any) -> None:
            msg = f"Postcondition '{pc.name}' failed (sync_warn)"
            self._warnings.append(msg)
            self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause=f"contract.postconditions.{pc.name}",
                evidence={"check": pc.check, "output_type": str(type(o).__name__)},
                severity=pc.severity,
                enforcement="warned",
            )

        return evaluate_postconditions(
            self._contract.postconditions, output, on_warn=on_warn
        )

    # --- Duration check ---

    def check_duration(self) -> None:
        """Check elapsed time against budget limit."""
        try:
            self._budget_tracker.check_duration()
        except BudgetExceededError as e:
            event = self._emitter.create_event(
                contract_id=self._contract.identity.name,
                contract_version=self._contract.identity.version,
                violated_clause="resources.budgets.max_duration_seconds",
                evidence={"current": e.current, "limit": e.limit},
                severity="critical",
                enforcement="blocked",
            )
            raise ContractViolation(str(e), event=event) from e

    # --- Context manager ---

    def __enter__(self) -> "ContractEnforcer":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


def enforce_contract(
    source: Union[str, Path],
    *,
    violation_destination: str = "stdout",
    strict: bool = True,
) -> Callable[[F], F]:
    """Decorator that wraps a function with contract enforcement.

    The decorated function receives a `_enforcer` keyword argument
    providing the ContractEnforcer instance for tool call checks.

    Input validation runs before the function.
    Output validation and postconditions run after.
    """
    contract = load_contract(source, strict=strict)

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            enforcer = ContractEnforcer(
                contract, violation_destination=violation_destination
            )
            # Only inject _enforcer if the function accepts it
            sig = inspect.signature(fn)
            if "_enforcer" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                kwargs["_enforcer"] = enforcer

            # Pre: validate input if first positional arg is present
            if args and contract.input_schema is not None:
                errors = enforcer.validate_input(args[0])
                if errors:
                    raise ContractViolation(
                        f"Input validation failed: {errors}"
                    )

            result = fn(*args, **kwargs)

            # Post: validate output
            if contract.output_schema is not None:
                errors = enforcer.validate_output(result)
                if errors:
                    enforcer._warnings.append(f"Output validation warnings: {errors}")

            # Post: evaluate postconditions
            enforcer.evaluate_postconditions(result)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
