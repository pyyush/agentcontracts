"""LangChain adapter — contract enforcement for LangChain agents.

Usage (3 lines):
    from agent_contracts.adapters.langchain import ContractCallbackHandler
    handler = ContractCallbackHandler.from_file("contract.yaml")
    agent.invoke({"input": "..."}, config={"callbacks": [handler]})
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agent_contracts.adapters._shared import (
    check_observed_effect,
    finalize_adapter_run,
    installed_package_version,
    raise_if_blocking_verdict,
)
from agent_contracts.enforcer import ContractEnforcer, ContractViolation, RunVerdict
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
    Validates outputs against the contract's output schema and writes a verdict.

    Run lifecycle:
    - the contract run id is allocated when this object is created
    - on_tool_start can block generic tools before execution
    - on_tool_start can also block inspectable native shell, file, and network
      effects when local tool wrappers use conventional names such as
      bash/read_file/write_file/web_fetch and pass the effect target as input
    - on_chain_end validates output, evaluates postconditions, and writes the
      verdict artifact
    - finalize_run() can be called from a surrounding exception handler to
      write a failed verdict for unexpected host errors
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
            host_name="langchain",
            host_version=installed_package_version("langchain-core"),
        )
        self._raise_on_violation = raise_on_violation
        self._observed_completion = False

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
            if not check_observed_effect(
                self._enforcer,
                tool_name=str(tool_name),
                tool_input=input_str,
            ):
                self._enforcer.check_tool_call(str(tool_name))
        except ContractViolation as exc:
            self.finalize_run(execution_error=exc)
            if self._raise_on_violation:
                raise

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Called when a tool finishes."""
        pass

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Called when the chain finishes — finalize the verdict artifact."""
        self._observed_completion = True
        verdict = self.finalize_run(output=outputs)
        raise_if_blocking_verdict(verdict, enabled=self._raise_on_violation)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Called when LLM finishes — track token usage."""
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            total = usage.get("total_tokens", 0)
            if total > 0:
                try:
                    self._enforcer.add_tokens(total)
                except ContractViolation as exc:
                    self.finalize_run(execution_error=exc)
                    if self._raise_on_violation:
                        raise

    def finalize_run(
        self,
        *,
        output: Any = None,
        extra_context: Optional[Dict[str, Any]] = None,
        artifact_path: Optional[Union[str, Path]] = None,
        execution_error: Optional[BaseException] = None,
    ) -> RunVerdict:
        """Write and return the schema-backed verdict artifact for this run."""
        observed_completion = self._observed_completion or output is not None or execution_error is not None
        return finalize_adapter_run(
            self._enforcer,
            adapter_name="LangChain adapter",
            observed_completion=observed_completion,
            output=output,
            extra_context=extra_context,
            artifact_path=artifact_path,
            execution_error=execution_error,
        )
