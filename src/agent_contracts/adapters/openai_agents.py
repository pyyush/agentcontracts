"""OpenAI Agents SDK adapter — contract enforcement via RunHooks.

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
from typing import Any, List, Optional, Union

from agent_contracts.enforcer import ContractEnforcer, ContractViolation
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent

try:
    from openai_agents import RunHooks
except ImportError:
    # Stub so the module can be imported without openai-agents
    class RunHooks:  # type: ignore[no-redef]
        """Stub for when openai-agents is not installed."""
        pass


class ContractRunHooks(RunHooks):  # type: ignore[misc]
    """OpenAI Agents SDK RunHooks that enforces an agent contract.

    Intercepts tool calls for effect gating and budget tracking.
    Tracks token usage from LLM responses.
    Evaluates postconditions on agent completion.
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
        except ContractViolation:
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
                self._enforcer.add_tokens(total)

    async def on_agent_start(
        self, context: Any, agent: Any
    ) -> None:
        """Called when an agent starts executing."""
        pass

    async def on_agent_end(
        self, context: Any, agent: Any, output: Any
    ) -> None:
        """Called when an agent finishes — evaluate postconditions."""
        try:
            self._enforcer.evaluate_postconditions(output)
        except Exception:
            if self._raise_on_violation:
                raise

    async def on_handoff(
        self, context: Any, input: Any
    ) -> None:
        """Called during agent handoffs — observe, don't enforce yet."""
        pass
