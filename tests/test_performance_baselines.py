"""Performance regression baselines for hot release paths."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

from agent_contracts.effects import EffectGuard
from agent_contracts.init_from_trace import generate_contract_from_traces
from agent_contracts.postconditions import evaluate_postconditions
from agent_contracts.types import (
    EffectsAuthorized,
    FilesystemAuthorization,
    PostconditionDef,
    ShellAuthorization,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINES_PATH = ROOT / "benchmarks" / "performance-baselines.json"


def _load_baselines() -> Dict[str, Any]:
    with BASELINES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _elapsed_ms(operation: Callable[[], Any]) -> float:
    start = time.perf_counter()
    operation()
    return (time.perf_counter() - start) * 1000


def _assert_within_budget(name: str, elapsed_ms: float, max_ms: float) -> None:
    assert elapsed_ms <= max_ms, (
        f"{name} took {elapsed_ms:.2f}ms, exceeding the {max_ms:.2f}ms "
        "release performance budget"
    )


def test_effect_checks_stay_within_release_baselines(tmp_path: Path) -> None:
    baselines = _load_baselines()["effect_checks"]
    guard = EffectGuard(
        EffectsAuthorized(
            tools=["search", "database.*", "browser.*"],
            network=["https://api.example.com/*", "https://*.trusted.test/*"],
            state_writes=["tickets.*", "run_state.*"],
            filesystem=FilesystemAuthorization(
                read=["src/**", "tests/**", "README.md"],
                write=["src/**", "tests/**"],
            ),
            shell=ShellAuthorization(
                commands=["python -m pytest tests/*", "python -m ruff check src"]
            ),
        ),
        repo_root=tmp_path,
    )
    operations: List[Callable[[], bool]] = [
        lambda: guard.check_tool("database.read"),
        lambda: guard.check_network("https://api.example.com/v1/search"),
        lambda: guard.check_state_write("tickets.status"),
        lambda: guard.check_file_read("src/agent.py"),
        lambda: guard.check_file_write("tests/test_agent.py"),
        lambda: guard.check_shell_command("python -m pytest tests/test_agent.py"),
    ]

    for checks in (1, 100, 10_000):
        budget = baselines[str(checks)]["max_ms"]

        def run_checks(checks: int = checks) -> None:
            for index in range(checks):
                assert operations[index % len(operations)]() is True

        elapsed = _elapsed_ms(run_checks)
        _assert_within_budget(f"{checks} effect checks", elapsed, budget)


def _postconditions(count: int) -> List[PostconditionDef]:
    checks = [
        'output.status == "ok"',
        "output.score >= 0.9",
        "len(output.items) == 5",
        'output.kind in ["contract", "verdict"]',
        "output.meta.run_id is not None",
    ]
    return [
        PostconditionDef(
            name=f"release_hot_path_{index}",
            check=checks[index % len(checks)],
            enforcement="sync_block",
            severity="critical",
        )
        for index in range(count)
    ]


def test_postcondition_sets_stay_within_release_baselines() -> None:
    baselines = _load_baselines()["postconditions"]
    output = {
        "status": "ok",
        "score": 0.95,
        "items": [1, 2, 3, 4, 5],
        "kind": "contract",
        "meta": {"run_id": "run_perf_001"},
    }

    for profile in ("small", "large"):
        budget = baselines[profile]
        postconditions = _postconditions(budget["count"])
        elapsed = _elapsed_ms(
            lambda postconditions=postconditions: evaluate_postconditions(
                postconditions, output
            )
        )
        _assert_within_budget(
            f"{profile} postcondition set ({budget['count']} checks)",
            elapsed,
            budget["max_ms"],
        )


def _trace_lines(count: int) -> Iterable[str]:
    for index in range(count):
        shard = index % 25
        payload = {
            "agent": {"name": "bench-agent", "version": "1.0.0"},
            "tool_calls": [{"name": f"tool.{shard}"}],
            "network_requests": [{"url": f"https://api.example.com/{shard}"}],
            "filesystem": {
                "read": [f"src/module_{shard}/input.py"],
                "write": [f"tests/module_{shard}/test_output.py"],
            },
            "shell_commands": [f"python -m pytest tests/module_{shard}"],
            "usage": {"cost_usd": 0.01, "total_tokens": 500 + shard},
            "duration_seconds": 2.0 + shard / 100,
        }
        yield json.dumps(payload)


def test_large_jsonl_trace_bootstrap_stays_within_release_baseline(tmp_path: Path) -> None:
    budget = _load_baselines()["trace_bootstrap"]["large_jsonl"]
    trace_path = tmp_path / "large-traces.jsonl"
    trace_path.write_text("\n".join(_trace_lines(budget["trace_count"])) + "\n", encoding="utf-8")

    contract: Dict[str, Any] = {}
    elapsed = _elapsed_ms(
        lambda: contract.update(
            generate_contract_from_traces(trace_path, agent_name="bench-agent")
        )
    )

    _assert_within_budget(
        f"bootstrap from {budget['trace_count']} JSONL traces",
        elapsed,
        budget["max_ms"],
    )
    assert contract["identity"]["name"] == "bench-agent"
    assert len(contract["effects"]["authorized"]["tools"]) == 25
    assert contract["resources"]["budgets"]["max_shell_commands"] == 2
