"""Generate contract skeletons from execution traces.

Reads JSONL trace files and infers:
- Identity from agent metadata
- Tool allowlist from observed tool calls
- Budget estimates from observed resource usage
- Postcondition candidates from output patterns
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import yaml


def _read_traces(source: Union[str, Path]) -> List[Dict[str, Any]]:
    """Read JSONL trace file, returning list of trace entries."""
    path = Path(source)
    traces: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for _line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # Skip malformed lines
    return traces


def _extract_tools(traces: List[Dict[str, Any]]) -> List[str]:
    """Extract unique tool names from traces."""
    tools: Set[str] = set()
    for trace in traces:
        # Support various trace formats
        if "tool_calls" in trace:
            for tc in trace["tool_calls"]:
                name = tc.get("name") or tc.get("tool") or tc.get("function", {}).get("name")
                if name:
                    tools.add(name)
        if "tool" in trace and "name" in trace:
            tools.add(trace["name"])
        if "type" in trace and trace["type"] == "tool_call":
            name = trace.get("name") or trace.get("tool_name")
            if name:
                tools.add(name)
    return sorted(tools)


def _extract_budgets(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Estimate budget limits from observed resource usage (with 20% headroom)."""
    max_cost = 0.0
    max_tokens = 0
    max_tool_calls = 0
    max_duration = 0.0

    for trace in traces:
        usage = trace.get("usage", {})
        cost = usage.get("cost_usd", 0) or trace.get("cost_usd", 0)
        tokens = usage.get("total_tokens", 0) or trace.get("total_tokens", 0)
        tool_calls = len(trace.get("tool_calls", []))
        duration = trace.get("duration_seconds", 0) or (trace.get("latency_ms") or 0) / 1000

        max_cost = max(max_cost, cost)
        max_tokens = max(max_tokens, tokens)
        max_tool_calls = max(max_tool_calls, tool_calls)
        max_duration = max(max_duration, duration)

    budgets: Dict[str, Any] = {}
    if max_cost > 0:
        budgets["max_cost_usd"] = round(max_cost * 1.2, 2)
    if max_tokens > 0:
        budgets["max_tokens"] = int(max_tokens * 1.2)
    if max_tool_calls > 0:
        budgets["max_tool_calls"] = int(max_tool_calls * 1.2) + 1
    if max_duration > 0:
        budgets["max_duration_seconds"] = round(max_duration * 1.2, 1)

    return budgets


def _extract_identity(traces: List[Dict[str, Any]]) -> Dict[str, str]:
    """Extract agent identity from traces."""
    for trace in traces:
        agent = trace.get("agent", {})
        if isinstance(agent, dict):
            name = agent.get("name")
            version = agent.get("version")
            if name:
                return {"name": name, "version": version or "0.1.0"}
        agent_name = trace.get("agent_name") or trace.get("agent_id")
        if agent_name:
            return {"name": agent_name, "version": "0.1.0"}

    return {"name": "unnamed-agent", "version": "0.1.0"}


def generate_contract_from_traces(
    source: Union[str, Path],
    *,
    agent_name: Optional[str] = None,
    agent_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a contract skeleton from execution traces.

    Returns a dict ready to be serialized as YAML.
    """
    traces = _read_traces(source)

    identity = _extract_identity(traces)
    if agent_name:
        identity["name"] = agent_name
    if agent_version:
        identity["version"] = agent_version

    tools = _extract_tools(traces)
    budgets = _extract_budgets(traces)

    contract: Dict[str, Any] = {
        "agent_contract": "0.1.0",
        "identity": identity,
        "contract": {
            "postconditions": [
                {
                    "name": "produces_output",
                    "check": "output is not None",
                    "enforcement": "sync_block",
                    "severity": "critical",
                    "description": "Agent must produce a non-null output.",
                }
            ]
        },
    }

    # Tier 1 fields (if we have data)
    if tools:
        contract["effects"] = {
            "authorized": {
                "tools": tools,
                "network": [],
                "state_writes": [],
            }
        }

    if budgets:
        contract["resources"] = {"budgets": budgets}

    return contract


def generate_contract_yaml(
    source: Union[str, Path],
    *,
    agent_name: Optional[str] = None,
    agent_version: Optional[str] = None,
) -> str:
    """Generate a contract YAML string from execution traces."""
    data = generate_contract_from_traces(
        source, agent_name=agent_name, agent_version=agent_version
    )
    return yaml.dump(data, sort_keys=False, default_flow_style=False)
