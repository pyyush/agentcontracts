"""OpenAI Agents SDK adapter — repo-local contract enforcement via RunHooks.

Usage (3 lines):
    from agent_contracts.adapters.openai_agents import ContractRunHooks
    hooks = ContractRunHooks.from_file("contract.yaml")
    result = await Runner.run(agent, "prompt", run_hooks=[hooks])

Requires: pip install aicontracts[openai]

Honest limitation: on_tool_start fires AFTER the LLM has already decided
to call the tool and spent reasoning tokens. Blocking here prevents
execution but not the token cost of the decision.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agent_contracts.adapters._shared import (
    finalize_adapter_run,
    installed_package_version,
    raise_if_blocking_verdict,
)
from agent_contracts.enforcer import ContractEnforcer, ContractViolation, RunVerdict
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent

try:
    from agents import RunHooks
except ImportError:
    # Stub so the module can be imported without openai-agents
    class RunHooks:  # type: ignore[no-redef]
        """Stub for when openai-agents is not installed."""
        pass


class ContractRunHooks(RunHooks):  # type: ignore[misc]
    """OpenAI Agents SDK RunHooks that enforces an agent contract.

    Intercepts tool calls for effect gating and budget tracking.
    Tracks token usage from LLM responses.
    Finalizes a verdict on agent completion.

    Run lifecycle:
    - the contract run id is allocated when this object is created
    - on_agent_start marks host execution as started
    - on_tool_start can block generic tool names before tool execution, after
      the model has already chosen the tool
    - file, shell, and network arguments are not visible in the OpenAI
      RunHooks surface used here; wrap those effects as named tools or rely on
      the CI verdict gate for post-run detection
    - on_agent_end validates output, evaluates postconditions, and writes the
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
            host_name="openai-agents",
            host_version=installed_package_version("openai-agents"),
        )
        self._raise_on_violation = raise_on_violation
        self._started = False
        self._observed_completion = False

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        *,
        violation_destination: str = "stdout",
        raise_on_violation: bool = True,
    ) -> "ContractRunHooks":
        """Create hooks from a contract YAML file."""
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

    async def on_tool_start(
        self, context: Any, agent: Any, tool: Any
    ) -> None:
        """Called before a tool executes — enforce effect authorization and budget.

        Raises ContractViolation to prevent unauthorized tool execution.
        Note: LLM reasoning tokens for this tool call are already spent.
        """
        tool_name = getattr(tool, "name", str(tool))
        try:
            self._enforcer.check_tool_call(tool_name)
        except ContractViolation as exc:
            self.finalize_run(execution_error=exc)
            if self._raise_on_violation:
                raise

    async def on_tool_end(
        self, context: Any, agent: Any, tool: Any, result: str
    ) -> None:
        """Called after a tool executes."""
        pass

    async def on_llm_start(
        self, context: Any, agent: Any, system_prompt: Any, input_items: Any
    ) -> None:
        """Called before an LLM invocation."""
        pass

    async def on_llm_end(
        self, context: Any, agent: Any, response: Any
    ) -> None:
        """Called after an LLM invocation — track token usage."""
        # Extract usage from the response object
        usage = getattr(response, "usage", None)
        if usage is not None:
            total = getattr(usage, "total_tokens", 0)
            if total and total > 0:
                try:
                    self._enforcer.add_tokens(total)
                except ContractViolation as exc:
                    self.finalize_run(execution_error=exc)
                    if self._raise_on_violation:
                        raise

    async def on_agent_start(
        self, context: Any, agent: Any
    ) -> None:
        """Called when an agent starts executing."""
        self._started = True

    async def on_agent_end(
        self, context: Any, agent: Any, output: Any
    ) -> None:
        """Called when an agent finishes — finalize the verdict artifact."""
        self._observed_completion = True
        verdict = self.finalize_run(output=output)
        raise_if_blocking_verdict(verdict, enabled=self._raise_on_violation)

    async def on_handoff(
        self, context: Any, input: Any
    ) -> None:
        """Called during agent handoffs — observe, don't enforce yet."""
        pass

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
            adapter_name="OpenAI Agents SDK adapter",
            observed_completion=observed_completion,
            output=output,
            extra_context=extra_context,
            artifact_path=artifact_path,
            execution_error=execution_error,
        )
