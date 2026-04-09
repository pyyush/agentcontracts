
"""Generate coding-agent contract skeletons from execution traces."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union, cast

import yaml


def _read_traces(source: Union[str, Path]) -> List[Dict[str, Any]]:
    path = Path(source)
    traces: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                traces.append(payload)
    return traces


def _iter_events(trace: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield trace
    events = trace.get("events", [])
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                yield event


def _extract_tools(traces: List[Dict[str, Any]]) -> List[str]:
    tools: Set[str] = set()
    for trace in traces:
        for entry in _iter_events(trace):
            tool_calls = entry.get("tool_calls", [])
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        name = tool_call.get("name") or tool_call.get("tool")
                        if name:
                            tools.add(str(name))
            if entry.get("type") == "tool_call":
                name = entry.get("name") or entry.get("tool_name")
                if name:
                    tools.add(str(name))
    return sorted(tools)


def _extract_network(traces: List[Dict[str, Any]]) -> List[str]:
    urls: Set[str] = set()
    for trace in traces:
        for entry in _iter_events(trace):
            for key in ("url", "endpoint"):
                value = entry.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    urls.add(value)
            requests = entry.get("network_requests", [])
            if isinstance(requests, list):
                for request in requests:
                    if isinstance(request, dict):
                        url = request.get("url")
                        if isinstance(url, str):
                            urls.add(url)
    return sorted(urls)


def _normalize_path(path: str) -> Optional[str]:
    candidate = path.strip()
    if not candidate:
        return None
    posix = PurePosixPath(candidate.lstrip("./"))
    if str(posix) == ".":
        return None
    return posix.as_posix()


def _infer_globs(paths: Set[str]) -> List[str]:
    patterns: Set[str] = set()
    for path in paths:
        normalized = _normalize_path(path)
        if normalized is None:
            continue
        parts = PurePosixPath(normalized).parts
        if len(parts) <= 1:
            patterns.add(normalized)
        else:
            patterns.add(f"{parts[0]}/**")
    return sorted(patterns)


def _extract_filesystem(traces: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    read_paths: Set[str] = set()
    write_paths: Set[str] = set()
    for trace in traces:
        for entry in _iter_events(trace):
            filesystem = entry.get("filesystem")
            if isinstance(filesystem, dict):
                for value in filesystem.get("read", []):
                    if isinstance(value, str):
                        read_paths.add(value)
                for value in filesystem.get("write", []):
                    if isinstance(value, str):
                        write_paths.add(value)
            for key in ("file_reads", "files_read", "read_paths"):
                values = entry.get(key, [])
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            read_paths.add(value)
            for key in ("file_writes", "files_written", "write_paths"):
                values = entry.get(key, [])
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            write_paths.add(value)
            event_type = entry.get("type")
            path_value = entry.get("path")
            if isinstance(path_value, str):
                if event_type in {"file_read", "filesystem.read"}:
                    read_paths.add(path_value)
                if event_type in {"file_write", "filesystem.write"}:
                    write_paths.add(path_value)
    result: Dict[str, List[str]] = {}
    read_globs = _infer_globs(read_paths)
    write_globs = _infer_globs(write_paths)
    if read_globs:
        result["read"] = read_globs
    if write_globs:
        result["write"] = write_globs
    return result


def _extract_shell_commands(traces: List[Dict[str, Any]]) -> Tuple[List[str], int]:
    commands: Set[str] = set()
    max_count = 0
    for trace in traces:
        count = 0
        for entry in _iter_events(trace):
            values = entry.get("shell_commands", [])
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        commands.add(" ".join(value.strip().split()))
                        count += 1
                    elif isinstance(value, dict) and isinstance(value.get("command"), str):
                        commands.add(" ".join(value["command"].strip().split()))
                        count += 1
            event_type = entry.get("type")
            command = entry.get("command")
            if event_type in {"shell", "shell_command", "command"} and isinstance(command, str):
                commands.add(" ".join(command.strip().split()))
                count += 1
        max_count = max(max_count, count)
    return sorted(commands), max_count


def _extract_budgets(traces: List[Dict[str, Any]], max_shell_commands: int) -> Dict[str, Any]:
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
        max_cost = max(max_cost, float(cost or 0))
        max_tokens = max(max_tokens, int(tokens or 0))
        max_tool_calls = max(max_tool_calls, int(tool_calls))
        max_duration = max(max_duration, float(duration or 0))

    budgets: Dict[str, Any] = {}
    if max_cost > 0:
        budgets["max_cost_usd"] = round(max_cost * 1.2, 2)
    if max_tokens > 0:
        budgets["max_tokens"] = int(max_tokens * 1.2)
    if max_tool_calls > 0:
        budgets["max_tool_calls"] = int(max_tool_calls * 1.2) + 1
    if max_duration > 0:
        budgets["max_duration_seconds"] = round(max_duration * 1.2, 1)
    if max_shell_commands > 0:
        budgets["max_shell_commands"] = int(max_shell_commands * 1.2) + 1
    return budgets


def _extract_identity(traces: List[Dict[str, Any]]) -> Dict[str, str]:
    for trace in traces:
        agent = trace.get("agent", {})
        if isinstance(agent, dict):
            name = agent.get("name")
            version = agent.get("version")
            if name:
                return {"name": str(name), "version": str(version or "0.1.0")}
        agent_name = trace.get("agent_name") or trace.get("agent_id")
        if agent_name:
            return {"name": str(agent_name), "version": "0.1.0"}
    return {"name": "unnamed-agent", "version": "0.1.0"}


def generate_contract_from_traces(
    source: Union[str, Path],
    *,
    agent_name: Optional[str] = None,
    agent_version: Optional[str] = None,
) -> Dict[str, Any]:
    traces = _read_traces(source)
    identity = _extract_identity(traces)
    if agent_name:
        identity["name"] = agent_name
    if agent_version:
        identity["version"] = agent_version

    tools = _extract_tools(traces)
    network = _extract_network(traces)
    filesystem = _extract_filesystem(traces)
    shell_commands, max_shell_commands = _extract_shell_commands(traces)
    budgets = _extract_budgets(traces, max_shell_commands)

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
        "observability": {
            "run_artifact_path": ".agent-contracts/runs/{run_id}/verdict.json"
        },
    }

    authorized: Dict[str, Any] = {
        "tools": tools,
        "network": network,
        "state_writes": [],
    }
    if filesystem:
        authorized["filesystem"] = filesystem
    if shell_commands:
        authorized["shell"] = {"commands": shell_commands}
    contract["effects"] = {"authorized": authorized}
    if budgets:
        contract["resources"] = {"budgets": budgets}
    return contract


def generate_contract_yaml(
    source: Union[str, Path],
    *,
    agent_name: Optional[str] = None,
    agent_version: Optional[str] = None,
) -> str:
    data = generate_contract_from_traces(
        source, agent_name=agent_name, agent_version=agent_version
    )
    return cast(str, yaml.dump(data, sort_keys=False, default_flow_style=False))
