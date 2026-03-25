"""Violation event creation and emission — OTel-compatible structured events.

Violation events are the core observability primitive for agent contracts.
Each event captures: what was violated, the evidence, severity, and trace context.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ViolationEvent:
    """A structured violation event (OTel-compatible)."""

    contract_id: str
    contract_version: str
    violated_clause: str
    evidence: Dict[str, Any]
    severity: str  # "critical", "major", "minor"
    enforcement: str  # "blocked", "warned", "monitored"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict for serialization."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    def to_otel_attributes(self) -> Dict[str, str]:
        """Convert to OTel event attributes (all string values)."""
        attrs: Dict[str, str] = {
            "agent_contract.id": self.contract_id,
            "agent_contract.version": self.contract_version,
            "agent_contract.violation.clause": self.violated_clause,
            "agent_contract.violation.severity": self.severity,
            "agent_contract.violation.enforcement": self.enforcement,
            "agent_contract.violation.event_id": self.event_id,
        }
        if self.evidence:
            attrs["agent_contract.violation.evidence"] = json.dumps(
                self.evidence, default=str
            )
        return attrs


class ViolationEmitter:
    """Emits violation events to configured destinations.

    Supports stdout (default), callback, and optional OTel SDK integration.
    """

    def __init__(
        self,
        destination: str = "stdout",
        callback: Optional[Callable[[ViolationEvent], None]] = None,
    ) -> None:
        self._destination = destination
        self._callback = callback
        self._events: List[ViolationEvent] = []
        self._lock = threading.Lock()

    @property
    def events(self) -> List[ViolationEvent]:
        """All events emitted during this emitter's lifetime (thread-safe copy)."""
        with self._lock:
            return list(self._events)

    def emit(self, event: ViolationEvent) -> None:
        """Emit a violation event (thread-safe)."""
        with self._lock:
            self._events.append(event)

        if self._destination == "stdout":
            print(
                f"[VIOLATION] {event.severity.upper()}: {event.violated_clause} "
                f"(contract={event.contract_id}@{event.contract_version}, "
                f"enforcement={event.enforcement})",
                file=sys.stderr,
            )
        elif self._destination == "otel":
            self._emit_otel(event)
        elif self._destination == "callback" and self._callback:
            self._callback(event)

    def _emit_otel(self, event: ViolationEvent) -> None:
        """Emit via OpenTelemetry SDK (if available)."""
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                span.add_event(
                    "agent_contract.violation",
                    attributes=event.to_otel_attributes(),
                )
            else:
                # Fallback to stdout if no active span
                print(
                    f"[VIOLATION/OTel-fallback] {event.to_json()}",
                    file=sys.stderr,
                )
        except ImportError:
            # OTel not installed — fallback to stdout
            print(
                f"[VIOLATION/OTel-unavailable] {event.to_json()}",
                file=sys.stderr,
            )

    def create_event(
        self,
        contract_id: str,
        contract_version: str,
        violated_clause: str,
        evidence: Dict[str, Any],
        severity: str = "major",
        enforcement: str = "warned",
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> ViolationEvent:
        """Create and emit a violation event in one call."""
        event = ViolationEvent(
            contract_id=contract_id,
            contract_version=contract_version,
            violated_clause=violated_clause,
            evidence=evidence,
            severity=severity,
            enforcement=enforcement,
            trace_id=trace_id,
            span_id=span_id,
        )
        self.emit(event)
        return event

    def clear(self) -> None:
        """Clear the event history (thread-safe)."""
        with self._lock:
            self._events.clear()
