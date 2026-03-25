"""Tests for violation events."""

from __future__ import annotations

import json

from agent_contracts.violations import ViolationEmitter, ViolationEvent


class TestViolationEvent:
    def test_creation(self) -> None:
        event = ViolationEvent(
            contract_id="test-agent",
            contract_version="1.0.0",
            violated_clause="budgets.max_cost_usd",
            evidence={"actual": 5.23, "limit": 5.00},
            severity="critical",
            enforcement="blocked",
        )
        assert event.contract_id == "test-agent"
        assert event.severity == "critical"
        assert event.event_id  # Auto-generated UUID

    def test_to_dict(self) -> None:
        event = ViolationEvent(
            contract_id="test",
            contract_version="1.0.0",
            violated_clause="effects.authorized.tools",
            evidence={"tool": "delete_all"},
            severity="critical",
            enforcement="blocked",
        )
        d = event.to_dict()
        assert d["contract_id"] == "test"
        assert "trace_id" not in d  # None values excluded

    def test_to_json(self) -> None:
        event = ViolationEvent(
            contract_id="test",
            contract_version="1.0.0",
            violated_clause="budgets.max_tokens",
            evidence={"actual": 15000, "limit": 10000},
            severity="major",
            enforcement="warned",
        )
        parsed = json.loads(event.to_json())
        assert parsed["violated_clause"] == "budgets.max_tokens"

    def test_to_otel_attributes(self) -> None:
        event = ViolationEvent(
            contract_id="agent-x",
            contract_version="2.0.0",
            violated_clause="postconditions.quality_check",
            evidence={"score": 0.3, "threshold": 0.8},
            severity="major",
            enforcement="warned",
        )
        attrs = event.to_otel_attributes()
        assert attrs["agent_contract.id"] == "agent-x"
        assert attrs["agent_contract.violation.severity"] == "major"
        assert "score" in attrs["agent_contract.violation.evidence"]

    def test_with_trace_context(self) -> None:
        event = ViolationEvent(
            contract_id="test",
            contract_version="1.0.0",
            violated_clause="test",
            evidence={},
            severity="minor",
            enforcement="monitored",
            trace_id="abc123",
            span_id="def456",
        )
        d = event.to_dict()
        assert d["trace_id"] == "abc123"
        assert d["span_id"] == "def456"


class TestViolationEmitter:
    def test_callback_emission(self) -> None:
        received: list = []
        emitter = ViolationEmitter(destination="callback", callback=lambda e: received.append(e))
        emitter.create_event(
            contract_id="test",
            contract_version="1.0.0",
            violated_clause="budgets.max_cost_usd",
            evidence={"actual": 5.0, "limit": 1.0},
            severity="critical",
            enforcement="blocked",
        )
        assert len(received) == 1
        assert received[0].violated_clause == "budgets.max_cost_usd"

    def test_events_accumulated(self) -> None:
        emitter = ViolationEmitter(destination="callback", callback=lambda e: None)
        emitter.create_event("a", "1.0.0", "clause1", {}, "major", "warned")
        emitter.create_event("a", "1.0.0", "clause2", {}, "minor", "monitored")
        assert len(emitter.events) == 2

    def test_clear_events(self) -> None:
        emitter = ViolationEmitter(destination="callback", callback=lambda e: None)
        emitter.create_event("a", "1.0.0", "clause1", {}, "major", "warned")
        emitter.clear()
        assert len(emitter.events) == 0

    def test_stdout_emission(self, capsys) -> None:
        emitter = ViolationEmitter(destination="stdout")
        emitter.create_event("test", "1.0.0", "budgets.max_tokens", {"actual": 15000}, "major", "warned")
        captured = capsys.readouterr()
        assert "VIOLATION" in captured.err
        assert "budgets.max_tokens" in captured.err
