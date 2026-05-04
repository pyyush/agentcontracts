"""Claude Agent SDK adapter — repo-local contract enforcement via hooks.

Usage (3 lines):
    from agent_contracts.adapters.claude_agent import ContractHooks
    hooks = ContractHooks.from_file("contract.yaml")
    # Pass hooks.pre_tool_use and hooks.post_tool_use to ClaudeAgentOptions

Requires: pip install aicontracts[claude] (Python 3.10+)

Design: PreToolUse returns structured deny (not exception) when a tool
is unauthorized. This layers ON TOP of the SDK's own allowed_tools
mechanism — it does not replace it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from agent_contracts.adapters._shared import (
    check_observed_effect,
    finalize_adapter_run,
    installed_package_version,
)
from agent_contracts.enforcer import ContractEnforcer, ContractViolation, RunVerdict
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent


class ContractHooks:
    """Claude Agent SDK hooks that enforce an agent contract.

    Generates async callables for PreToolUse and PostToolUse that can be
    passed to ClaudeAgentOptions hooks configuration.

    Run lifecycle:
    - the contract run id is allocated when this object is created
    - PreToolUse can block generic tools before execution
    - PreToolUse can also block inspectable native file, shell, and network
      effects for common Claude tool payloads (Read/Write/Edit/Bash/WebFetch)
    - PostToolUse currently observes completion only
    - callers must call finalize_run() after the query loop, preferably in a
      finally block; track_result() marks the host completion observed but does
      not finalize by itself
    """

    def __init__(
        self,
        contract: Contract,
        *,
        violation_destination: str = "stdout",
        violation_callback: Optional[Callable[[ViolationEvent], None]] = None,
    ) -> None:
        self._enforcer = ContractEnforcer(
            contract,
            violation_destination=violation_destination,
            violation_callback=violation_callback,
            host_name="claude-agent-sdk",
            host_version=installed_package_version("claude-agent-sdk"),
        )
        self._observed_completion = False

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        *,
        violation_destination: str = "stdout",
    ) -> "ContractHooks":
        """Create hooks from a contract YAML file."""
        contract = load_contract(path)
        return cls(contract, violation_destination=violation_destination)

    @property
    def enforcer(self) -> ContractEnforcer:
        return self._enforcer

    @property
    def violations(self) -> List[ViolationEvent]:
        return self._enforcer.violations

    async def pre_tool_use(
        self,
        input_data: Dict[str, Any],
        tool_use_id: Optional[str] = None,
        context: Any = None,
    ) -> Dict[str, Any]:
        """PreToolUse hook — check authorization before tool executes.

        Returns structured deny if tool is not authorized.
        Returns empty dict to allow execution.
        """
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        try:
            if not check_observed_effect(
                self._enforcer,
                tool_name=str(tool_name),
                tool_input=tool_input,
            ):
                self._enforcer.check_tool_call(str(tool_name))
        except ContractViolation as exc:
            return {
                "hookSpecificOutput": {
                    "hookEventName": input_data.get("hook_event_name", "PreToolUse"),
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{exc} Agent contract: "
                        f"'{self._enforcer.contract.identity.name}'"
                    ),
                }
            }

        return {}

    async def post_tool_use(
        self,
        input_data: Dict[str, Any],
        tool_use_id: Optional[str] = None,
        context: Any = None,
    ) -> Dict[str, Any]:
        """PostToolUse hook — observe tool completion."""
        return {}

    def get_hooks_config(self) -> Dict[str, Any]:
        """Return a hooks dict suitable for ClaudeAgentOptions.

        Usage:
            options = ClaudeAgentOptions(hooks=contract_hooks.get_hooks_config())
        """
        return {
            "PreToolUse": [{"hooks": [self.pre_tool_use]}],
            "PostToolUse": [{"hooks": [self.post_tool_use]}],
        }

    def track_result(self, result_message: Any) -> None:
        """Extract cost and token usage from a ResultMessage.

        Call this after the agent run completes:
            async for message in query(prompt="..."):
                if hasattr(message, 'total_cost_usd'):
                    hooks.track_result(message)
        """
        self._observed_completion = True
        cost = getattr(result_message, "total_cost_usd", None)
        try:
            if cost is not None and cost > 0:
                self._enforcer.add_cost(cost)

            usage = getattr(result_message, "usage", None)
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total = input_tokens + output_tokens
                if total > 0:
                    self._enforcer.add_tokens(total)
        except ContractViolation as exc:
            self.finalize_run(execution_error=exc)
            raise

    def finalize_run(
        self,
        *,
        output: Any = None,
        extra_context: Optional[Dict[str, Any]] = None,
        artifact_path: Optional[Union[str, Path]] = None,
        execution_error: Optional[BaseException] = None,
    ) -> RunVerdict:
        """Write and return the schema-backed verdict artifact for this run.

        Pass the final agent output whenever the host exposes it. If no output
        or execution error is supplied before completion is observed, the
        verdict records a required adapter observation failure instead of
        silently passing.
        """
        observed_completion = self._observed_completion or output is not None or execution_error is not None
        return finalize_adapter_run(
            self._enforcer,
            adapter_name="Claude Agent SDK adapter",
            observed_completion=observed_completion,
            output=output,
            extra_context=extra_context,
            artifact_path=artifact_path,
            execution_error=execution_error,
        )
