"""Shared test fixtures for Agent Contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml


@pytest.fixture
def tmp_yaml(tmp_path: Path):
    """Factory fixture — write a dict as YAML and return the path."""

    def _write(data: Dict[str, Any], name: str = "contract.yaml") -> Path:
        path = tmp_path / name
        path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def tier0_data() -> Dict[str, Any]:
    """Minimal Tier 0 contract (4 fields)."""
    return {
        "agent_contract": "0.1.0",
        "identity": {"name": "test-agent", "version": "1.0.0"},
        "contract": {
            "postconditions": [
                {"name": "has_output", "check": "output is not None"}
            ]
        },
    }


@pytest.fixture
def tier1_data(tier0_data: Dict[str, Any]) -> Dict[str, Any]:
    """Tier 1 contract with coding/build authorization surfaces."""
    return {
        **tier0_data,
        "inputs": {"schema": {"type": "object", "properties": {"query": {"type": "string"}}}},
        "outputs": {"schema": {"type": "object", "properties": {"result": {"type": "string"}}}},
        "effects": {
            "authorized": {
                "tools": ["search", "database.read"],
                "network": ["https://api.example.com/*"],
                "state_writes": [],
                "filesystem": {
                    "read": ["src/**", "tests/**", "README.md"],
                    "write": ["src/**", "tests/**"],
                },
                "shell": {"commands": ["python -m pytest *", "python -m ruff check *"]},
            }
        },
        "resources": {
            "budgets": {
                "max_cost_usd": 0.50,
                "max_tokens": 10000,
                "max_tool_calls": 20,
                "max_duration_seconds": 30.0,
                "max_shell_commands": 5,
            }
        },
    }


@pytest.fixture
def tier2_data(tier1_data: Dict[str, Any]) -> Dict[str, Any]:
    """Tier 2 contract with composable fields and verdict artifact path."""
    return {
        **tier1_data,
        "effects": {
            **tier1_data["effects"],
            "declared": {
                "tools": ["search"],
                "network": ["https://api.example.com/search"],
                "state_writes": [],
            },
        },
        "failure_model": {
            "errors": [
                {"name": "timeout", "retryable": True, "max_retries": 3},
                {"name": "rate_limit", "retryable": True, "max_retries": 2, "fallback": "cache-agent"},
            ],
            "default_timeout_seconds": 30.0,
            "circuit_breaker": {"failure_threshold": 5, "reset_timeout_seconds": 60.0},
        },
        "delegation": {
            "max_depth": 2,
            "attenuate_effects": True,
            "require_contract": True,
            "allowed_agents": ["cache-agent", "summarizer"],
        },
        "observability": {
            "traces": {"enabled": True, "sample_rate": 1.0},
            "metrics": [
                {"name": "tool_calls_total", "type": "counter"},
                {"name": "latency_ms", "type": "histogram"},
            ],
            "violation_events": {"emit": True, "destination": "otel"},
            "run_artifact_path": ".agent-contracts/runs/{run_id}/verdict.json",
        },
        "versioning": {
            "build_id": "sha256:abc123",
            "breaking_changes": [],
            "substitution": {"compatible_with": ["0.9.0"]},
        },
        "slo": {
            "contract_satisfaction_rate": {"target": 0.995, "window": "24h"},
            "latency": {"p50_ms": 500, "p99_ms": 5000},
            "cost": {"avg_usd": 0.10, "p99_usd": 0.50},
            "error_budget_policy": "alert_only",
        },
    }
