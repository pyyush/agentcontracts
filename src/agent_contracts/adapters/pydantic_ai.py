"""Pydantic AI adapter — contract enforcement for Pydantic AI agents.

Usage (3 lines):
    from agent_contracts.adapters.pydantic_ai import ContractMiddleware
    middleware = ContractMiddleware.from_file("contract.yaml")
    result = await middleware.run(agent, "user prompt")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Union

from agent_contracts.enforcer import ContractEnforcer, ContractViolation
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent


class ContractMiddleware:
    """Middleware that wraps Pydantic AI agent execution with contract enforcement.

    Intercepts tool calls for effect gating, tracks budgets,
    and validates outputs against the contract schema and postconditions.
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
    ) -> "ContractMiddleware":
        """Create middleware from a contract YAML file."""
        contract = load_contract(path)
        return cls(contract, violation_destination=violation_destination,
                   violation_callback=violation_callback)

    @property
    def enforcer(self) -> ContractEnforcer:
        return self._enforcer

    @property
    def violations(self) -> List[ViolationEvent]:
        return self._enforcer.violations

    def check_tool(self, tool_name: str) -> None:
        """Check if a tool is authorized by the contract."""
        self._enforcer.check_tool_call(tool_name)

    def validate_result(self, result: Any) -> List[str]:
        """Validate agent result against contract."""
        output = result
        if hasattr(result, "data"):
            output = result.data
        if hasattr(result, "output"):
            output = result.output

        errors = self._enforcer.validate_output(
            output if isinstance(output, dict) else {"result": output}
        )
        self._enforcer.evaluate_postconditions(output)
        return errors

    async def run(self, agent: Any, prompt: str, **kwargs: Any) -> Any:
        """Run a Pydantic AI agent with contract enforcement.

        Wraps agent.run() with pre/post validation.
        """
        # Validate input
        if self._contract.input_schema:
            input_data = {"prompt": prompt, **kwargs}
            input_errors = self._enforcer.validate_input(input_data)
            if input_errors:
                raise ContractViolation(f"Input validation failed: {input_errors}")

        # Execute agent
        result = await agent.run(prompt, **kwargs)

        # Validate output
        self.validate_result(result)

        return result

    def run_sync(self, agent: Any, prompt: str, **kwargs: Any) -> Any:
        """Synchronous version of run() for non-async contexts."""
        if self._contract.input_schema:
            input_data = {"prompt": prompt, **kwargs}
            input_errors = self._enforcer.validate_input(input_data)
            if input_errors:
                raise ContractViolation(f"Input validation failed: {input_errors}")

        result = agent.run_sync(prompt, **kwargs)
        self.validate_result(result)
        return result

    def wrap_tool(self, tool_fn: Callable[..., Any], tool_name: str) -> Callable[..., Any]:
        """Wrap a tool function with contract enforcement."""

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self._enforcer.check_tool_call(tool_name)
            return tool_fn(*args, **kwargs)

        wrapped.__name__ = tool_fn.__name__
        wrapped.__doc__ = tool_fn.__doc__
        return wrapped
