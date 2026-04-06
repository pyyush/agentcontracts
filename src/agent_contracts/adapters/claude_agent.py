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

from agent_contracts.enforcer import ContractEnforcer, ContractViolation
from agent_contracts.loader import load_contract
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEvent


class ContractHooks:
    """Claude Agent SDK hooks that enforce an agent contract.

    Generates async callables for PreToolUse and PostToolUse that can be
    passed to ClaudeAgentOptions hooks configuration.

    PreToolUse returns structured deny for unauthorized tools.
    PostToolUse tracks tool calls against budget.
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
        )

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

        try:
            self._enforcer.check_tool_call(tool_name)
        except ContractViolation:
            return {
                "hookSpecificOutput": {
                    "hookEventName": input_data.get("hook_event_name", "PreToolUse"),
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Tool '{tool_name}' not authorized by agent contract "
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
        cost = getattr(result_message, "total_cost_usd", None)
        if cost is not None and cost > 0:
            self._enforcer.add_cost(cost)

        usage = getattr(result_message, "usage", None)
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total = input_tokens + output_tokens
            if total > 0:
                self._enforcer.add_tokens(total)
