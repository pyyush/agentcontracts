"""CrewAI adapter — contract enforcement for CrewAI agents and crews.

Usage (3 lines):
    from agent_contracts.adapters.crewai import ContractGuard
    guard = ContractGuard.from_file("contract.yaml")
    result = guard.execute(crew, inputs={"query": "..."})
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from agent_contracts.enforcer import ContractEnforcer, ContractViolation
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent


class ContractGuard:
    """Wraps a CrewAI crew or agent with contract enforcement.

    Provides pre-execution input validation, tool call interception,
    and post-execution output validation with postconditions.
    """

    def __init__(
        self,
        contract: Contract,
        *,
        violation_destination: str = "stdout",
        violation_callback: Optional[Callable[[ViolationEvent], None]] = None,
    ) -> None:
        self._contract = contract
        self._enforcer = ContractEnforcer(
            contract,
            violation_destination=violation_destination,
            violation_callback=violation_callback,
        )

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        *,
        violation_destination: str = "stdout",
        violation_callback: Optional[Callable[[ViolationEvent], None]] = None,
    ) -> "ContractGuard":
        """Create a guard from a contract YAML file."""
        contract = load_contract(path)
        return cls(contract, violation_destination=violation_destination,
                   violation_callback=violation_callback)

    @property
    def enforcer(self) -> ContractEnforcer:
        return self._enforcer

    @property
    def violations(self) -> List[ViolationEvent]:
        return self._enforcer.violations

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs before crew execution."""
        return self._enforcer.validate_input(inputs)

    def check_tool(self, tool_name: str) -> None:
        """Check if a tool is authorized by the contract."""
        self._enforcer.check_tool_call(tool_name)

    def validate_output(self, output: Any) -> List[str]:
        """Validate output after crew execution."""
        errors = self._enforcer.validate_output(output)
        self._enforcer.evaluate_postconditions(output)
        return errors

    def execute(self, crew: Any, *, inputs: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a crew with contract enforcement.

        Validates inputs before execution and outputs/postconditions after.
        """
        if inputs is not None:
            input_errors = self.validate_inputs(inputs)
            if input_errors:
                raise ContractViolation(f"Input validation failed: {input_errors}")

        # Execute the crew
        result = crew.kickoff(inputs=inputs)

        # Post-execution validation
        output = result if not hasattr(result, "raw") else result.raw
        self._enforcer.validate_output(output if isinstance(output, dict) else {"result": output})
        self._enforcer.evaluate_postconditions(output)

        return result

    def wrap_tool(self, tool_fn: Callable[..., Any], tool_name: str) -> Callable[..., Any]:
        """Wrap a tool function with contract enforcement."""

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self._enforcer.check_tool_call(tool_name)
            return tool_fn(*args, **kwargs)

        wrapped.__name__ = tool_fn.__name__  # type: ignore[attr-defined]
        wrapped.__doc__ = tool_fn.__doc__
        return wrapped
