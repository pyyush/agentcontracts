"""LangChain adapter — contract enforcement for LangChain agents.

Usage (3 lines):
    from agent_contracts.adapters.langchain import ContractCallbackHandler
    handler = ContractCallbackHandler.from_file("contract.yaml")
    agent.invoke({"input": "..."}, config={"callbacks": [handler]})
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from agent_contracts.enforcer import ContractEnforcer, ContractViolation
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:
    # Provide a stub so the module can be imported without langchain
    class BaseCallbackHandler:  # type: ignore[no-redef]
        """Stub for when langchain-core is not installed."""
        pass


class ContractCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """LangChain callback handler that enforces an agent contract.

    Intercepts tool calls for effect gating and budget tracking.
    Validates outputs against the contract's output schema.
    """

    def __init__(
        self,
        contract: Contract,
        *,
        violation_destination: str = "stdout",
        violation_callback: Optional[Any] = None,
        raise_on_violation: bool = True,
    ) -> None:
        self._enforcer = ContractEnforcer(
            contract,
            violation_destination=violation_destination,
            violation_callback=violation_callback,
        )
        self._raise_on_violation = raise_on_violation

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        *,
        violation_destination: str = "stdout",
        raise_on_violation: bool = True,
    ) -> "ContractCallbackHandler":
        """Create a handler from a contract YAML file."""
        contract = load_contract(path)
        return cls(
            contract,
            violation_destination=violation_destination,
            raise_on_violation=raise_on_violation,
        )

    @property
    def enforcer(self) -> ContractEnforcer:
        return self._enforcer

    @property
    def violations(self) -> List[ViolationEvent]:
        return self._enforcer.violations

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts — enforce effect authorization and budget."""
        tool_name = serialized.get("name", "")
        try:
            self._enforcer.check_tool_call(tool_name)
        except ContractViolation:
            if self._raise_on_violation:
                raise

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Called when a tool finishes."""
        pass

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Called when the chain finishes — validate output and postconditions."""
        output_errors = self._enforcer.validate_output(outputs)
        if output_errors and self._raise_on_violation:
            raise ContractViolation(f"Output validation failed: {output_errors}")

        self._enforcer.evaluate_postconditions(outputs)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Called when LLM finishes — track token usage."""
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            total = usage.get("total_tokens", 0)
            if total > 0:
                self._enforcer.add_tokens(total)
