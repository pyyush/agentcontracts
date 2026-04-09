
"""Runtime enforcement middleware for repo-local coding-agent contracts."""

from __future__ import annotations

import functools
import inspect
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, TypeVar, Union, cast

import jsonschema

from agent_contracts.budgets import BudgetExceededError, BudgetSnapshot, BudgetTracker
from agent_contracts.effects import EffectGuard
from agent_contracts.loader import load_contract
from agent_contracts.postconditions import (
    PostconditionError,
    PostconditionResult,
    PreconditionError,
    PreconditionResult,
    evaluate_postconditions,
    evaluate_preconditions,
)
from agent_contracts.types import Contract
from agent_contracts.violations import ViolationEmitter, ViolationEvent

F = TypeVar("F", bound=Callable[..., Any])
CheckStatus = Literal["pass", "warn", "fail", "blocked", "skipped"]


@dataclass(frozen=True)
class RunCheckResult:
    """Result for a named repo check or final gate check."""

    name: str
    status: CheckStatus
    required: bool = True
    exit_code: Optional[int] = None
    detail: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "required": self.required,
        }
        if self.exit_code is not None:
            data["exit_code"] = self.exit_code
        if self.detail is not None:
            data["detail"] = self.detail
        if self.evidence:
            data["evidence"] = self.evidence
        return data

    def to_context(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "required": self.required,
            "exit_code": self.exit_code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RunVerdict:
    """Durable verdict artifact for a contract-governed run."""

    run_id: str
    contract: Dict[str, Any]
    host: Dict[str, Any]
    outcome: Literal["pass", "warn", "blocked", "fail"]
    final_gate: Literal["allowed", "blocked", "failed"]
    violations: List[Dict[str, Any]]
    checks: List[RunCheckResult]
    budgets: Dict[str, Any]
    artifacts: Dict[str, Any]
    timestamp: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "contract": self.contract,
            "host": self.host,
            "outcome": self.outcome,
            "final_gate": self.final_gate,
            "violations": self.violations,
            "checks": [check.to_dict() for check in self.checks],
            "budgets": self.budgets,
            "artifacts": self.artifacts,
            "timestamp": self.timestamp,
            "warnings": self.warnings,
        }

    def write_json(self, destination: Union[str, Path]) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path


class ContractViolation(Exception):
    """Wraps any contract violation with context."""

    def __init__(self, message: str, event: Optional[ViolationEvent] = None) -> None:
        super().__init__(message)
        self.event = event


def load_verdict_artifact(source: Union[str, Path]) -> Dict[str, Any]:
    """Load a JSON verdict artifact from disk."""
    return cast(Dict[str, Any], json.loads(Path(source).read_text(encoding="utf-8")))


class ContractEnforcer:
    """Unified runtime enforcement for an agent contract."""

    def __init__(
        self,
        contract: Contract,
        *,
        violation_destination: str = "stdout",
        violation_callback: Optional[Callable[[ViolationEvent], None]] = None,
        cost_callback: Optional[Callable[[], float]] = None,
        repo_root: Optional[Union[str, Path]] = None,
        host_name: str = "unknown",
        host_version: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self._contract = contract
        self._repo_root = self._resolve_repo_root(repo_root)
        self._effect_guard = EffectGuard(contract.effects_authorized, repo_root=self._repo_root)
        self._budget_tracker = BudgetTracker(contract.budgets, cost_callback=cost_callback)
        self._emitter = ViolationEmitter(
            destination=violation_destination, callback=violation_callback
        )
        self._warnings: List[str] = []
        self._checks: Dict[str, RunCheckResult] = {}
        self._run_id = run_id or str(uuid.uuid4())
        self._host_name = host_name
        self._host_version = host_version
        self._blocked = False
        self._postcondition_failure: Optional[PostconditionError] = None
        self._postconditions_evaluated = False
        self._last_output: Any = None
        self._last_extra_context: Optional[Dict[str, Any]] = None
        self._finalized_verdict: Optional[RunVerdict] = None
        self._artifact_path: Optional[Path] = None

    def _resolve_repo_root(self, repo_root: Optional[Union[str, Path]]) -> Path:
        if repo_root is not None:
            return Path(repo_root).resolve()
        if self._contract.source_path is not None:
            return Path(self._contract.source_path).resolve().parent
        return Path.cwd().resolve()

    @property
    def contract(self) -> Contract:
        return self._contract

    @property
    def budget_tracker(self) -> BudgetTracker:
        return self._budget_tracker

    @property
    def violations(self) -> List[ViolationEvent]:
        return self._emitter.events

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    @property
    def checks(self) -> List[RunCheckResult]:
        return list(self._checks.values())

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def artifact_path(self) -> Optional[Path]:
        return self._artifact_path

    @property
    def finalized_verdict(self) -> Optional[RunVerdict]:
        return self._finalized_verdict

    def _check_context(self) -> Dict[str, Dict[str, Any]]:
        return {name: result.to_context() for name, result in self._checks.items()}

    def _record_blocked_event(
        self,
        *,
        clause: str,
        evidence: Dict[str, Any],
        message: str,
        severity: str = "critical",
    ) -> None:
        self._blocked = True
        event = self._emitter.create_event(
            contract_id=self._contract.identity.name,
            contract_version=self._contract.identity.version,
            violated_clause=clause,
            evidence=evidence,
            severity=severity,
            enforcement="blocked",
        )
        raise ContractViolation(message, event=event)

    def _record_failed_event(
        self,
        *,
        clause: str,
        evidence: Dict[str, Any],
        severity: str = "critical",
    ) -> None:
        self._emitter.create_event(
            contract_id=self._contract.identity.name,
            contract_version=self._contract.identity.version,
            violated_clause=clause,
            evidence=evidence,
            severity=severity,
            enforcement="failed",
        )

    def _record_warn_event(
        self,
        *,
        clause: str,
        evidence: Dict[str, Any],
        severity: str = "major",
    ) -> None:
        self._emitter.create_event(
            contract_id=self._contract.identity.name,
            contract_version=self._contract.identity.version,
            violated_clause=clause,
            evidence=evidence,
            severity=severity,
            enforcement="warned",
        )

    def check_preconditions(self, input_data: Any) -> List[PreconditionResult]:
        if not self._contract.preconditions:
            return []
        try:
            return evaluate_preconditions(
                self._contract.preconditions, input_data, raise_on_failure=True
            )
        except PreconditionError as exc:
            self._record_blocked_event(
                clause=f"inputs.preconditions.{exc.precondition.name}",
                evidence={"check": exc.precondition.check},
                message=str(exc),
            )
        raise AssertionError("unreachable")

    def validate_input(self, input_data: Any) -> List[str]:
        if self._contract.input_schema is None:
            return []
        validator = jsonschema.Draft202012Validator(self._contract.input_schema)
        errors = [e.message for e in validator.iter_errors(input_data)]
        if errors:
            self._record_warn_event(
                clause="inputs.schema",
                evidence={
                    "errors": errors,
                    "input_type": type(input_data).__name__,
                },
            )
        return errors

    def check_tool_call(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> None:
        del args
        if not self._effect_guard.check_tool(tool_name):
            self._record_blocked_event(
                clause="effects.authorized.tools",
                evidence={
                    "tool": tool_name,
                    "authorized": self._contract.effects_authorized.tools
                    if self._contract.effects_authorized
                    else [],
                },
                message=f"Tool '{tool_name}' not authorized by contract.",
            )
        try:
            self._budget_tracker.record_tool_call()
        except BudgetExceededError as exc:
            self._record_blocked_event(
                clause=f"resources.budgets.max_{exc.budget_type}"
                if exc.budget_type == "tool_calls"
                else f"resources.budgets.{exc.budget_type}",
                evidence={"current": exc.current, "limit": exc.limit},
                message=str(exc),
            )

    def check_network_request(self, url: str) -> None:
        if not self._effect_guard.check_network(url):
            self._record_blocked_event(
                clause="effects.authorized.network",
                evidence={
                    "url": url,
                    "authorized": self._contract.effects_authorized.network
                    if self._contract.effects_authorized
                    else [],
                },
                message=f"Network request '{url}' not authorized by contract.",
            )

    def check_state_write(self, scope: str) -> None:
        if not self._effect_guard.check_state_write(scope):
            self._record_blocked_event(
                clause="effects.authorized.state_writes",
                evidence={
                    "scope": scope,
                    "authorized": self._contract.effects_authorized.state_writes
                    if self._contract.effects_authorized
                    else [],
                },
                message=f"State write '{scope}' not authorized by contract.",
            )

    def check_file_read(self, path: Union[str, Path]) -> None:
        candidate = str(path)
        if not self._effect_guard.check_file_read(candidate):
            patterns: List[str] = []
            if (
                self._contract.effects_authorized is not None
                and self._contract.effects_authorized.filesystem is not None
            ):
                patterns = self._contract.effects_authorized.filesystem.read
            self._record_blocked_event(
                clause="effects.authorized.filesystem.read",
                evidence={"path": candidate, "authorized": patterns},
                message=f"File read '{candidate}' not authorized by contract.",
            )

    def check_file_write(self, path: Union[str, Path]) -> None:
        candidate = str(path)
        if not self._effect_guard.check_file_write(candidate):
            patterns: List[str] = []
            if (
                self._contract.effects_authorized is not None
                and self._contract.effects_authorized.filesystem is not None
            ):
                patterns = self._contract.effects_authorized.filesystem.write
            self._record_blocked_event(
                clause="effects.authorized.filesystem.write",
                evidence={"path": candidate, "authorized": patterns},
                message=f"File write '{candidate}' not authorized by contract.",
            )

    def check_shell_command(self, command: str) -> None:
        if not self._effect_guard.check_shell_command(command):
            patterns: List[str] = []
            if (
                self._contract.effects_authorized is not None
                and self._contract.effects_authorized.shell is not None
            ):
                patterns = self._contract.effects_authorized.shell.commands
            self._record_blocked_event(
                clause="effects.authorized.shell.commands",
                evidence={"command": command, "authorized": patterns},
                message=f"Shell command '{command}' not authorized by contract.",
            )
        try:
            self._budget_tracker.record_shell_command()
        except BudgetExceededError as exc:
            self._record_blocked_event(
                clause="resources.budgets.max_shell_commands",
                evidence={"current": exc.current, "limit": exc.limit},
                message=str(exc),
            )

    def add_cost(self, amount: float) -> None:
        try:
            self._budget_tracker.add_cost(amount)
        except BudgetExceededError as exc:
            self._record_blocked_event(
                clause="resources.budgets.max_cost_usd",
                evidence={"current": exc.current, "limit": exc.limit},
                message=str(exc),
            )

    def add_tokens(self, count: int) -> None:
        try:
            self._budget_tracker.add_tokens(count)
        except BudgetExceededError as exc:
            self._record_blocked_event(
                clause="resources.budgets.max_tokens",
                evidence={"current": exc.current, "limit": exc.limit},
                message=str(exc),
            )

    def validate_output(self, output_data: Any) -> List[str]:
        if self._contract.output_schema is None:
            return []
        validator = jsonschema.Draft202012Validator(self._contract.output_schema)
        errors = [e.message for e in validator.iter_errors(output_data)]
        if errors:
            self._warnings.append(f"Output validation warnings: {errors}")
            self._record_warn_event(
                clause="outputs.schema",
                evidence={"errors": errors},
            )
        return errors

    def evaluate_postconditions(
        self,
        output: Any,
        *,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> List[PostconditionResult]:
        self._last_output = output
        self._last_extra_context = extra_context
        merged_context: Dict[str, Any] = {"checks": self._check_context()}
        if extra_context:
            merged_context.update(extra_context)

        def on_warn(postcondition: Any, _: Any) -> None:
            message = f"Postcondition '{postcondition.name}' failed (sync_warn)"
            self._warnings.append(message)
            self._record_warn_event(
                clause=f"contract.postconditions.{postcondition.name}",
                evidence={
                    "check": postcondition.check,
                    "checks": self._check_context(),
                },
                severity=postcondition.severity,
            )

        results: List[PostconditionResult]
        try:
            results = evaluate_postconditions(
                self._contract.postconditions,
                output,
                extra_context=merged_context,
                on_warn=on_warn,
            )
        except PostconditionError as exc:
            self._postconditions_evaluated = True
            self._postcondition_failure = exc
            self._record_failed_event(
                clause=f"contract.postconditions.{exc.postcondition.name}",
                evidence={
                    "check": exc.postcondition.check,
                    "checks": self._check_context(),
                    "output_type": type(output).__name__,
                },
                severity=exc.postcondition.severity,
            )
            raise
        self._postconditions_evaluated = True
        return results

    def record_check(
        self,
        name: str,
        status: CheckStatus,
        *,
        exit_code: Optional[int] = None,
        detail: Optional[str] = None,
        required: bool = True,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> RunCheckResult:
        allowed: List[str] = ["pass", "warn", "fail", "blocked", "skipped"]
        if status not in allowed:
            raise ValueError(f"Unsupported check status: {status}")
        result = RunCheckResult(
            name=name,
            status=status,
            required=required,
            exit_code=exit_code,
            detail=detail,
            evidence=evidence or {},
        )
        self._checks[name] = result
        if status == "warn":
            self._warnings.append(f"Check '{name}' reported warning")
        return result

    def check_duration(self) -> None:
        try:
            self._budget_tracker.check_duration()
        except BudgetExceededError as exc:
            self._record_blocked_event(
                clause="resources.budgets.max_duration_seconds",
                evidence={"current": exc.current, "limit": exc.limit},
                message=str(exc),
            )

    def _default_artifact_path(self) -> str:
        return ".agent-contracts/runs/{run_id}/verdict.json"

    def _resolved_artifact_path(self, artifact_path: Optional[Union[str, Path]]) -> Path:
        raw = (
            str(artifact_path)
            if artifact_path is not None
            else (
                self._contract.observability.run_artifact_path
                if self._contract.observability and self._contract.observability.run_artifact_path
                else self._default_artifact_path()
            )
        )
        formatted = raw.format(run_id=self._run_id)
        path = Path(formatted)
        if not path.is_absolute():
            path = self._repo_root / path
        return path.resolve()

    def _snapshot_budgets(self) -> Dict[str, Any]:
        snapshot: BudgetSnapshot = self._budget_tracker.snapshot()
        return {
            "cost_usd": snapshot.cost_usd,
            "tokens": snapshot.tokens,
            "tool_calls": snapshot.tool_calls,
            "shell_commands": snapshot.shell_commands,
            "duration_seconds": snapshot.elapsed_seconds,
        }

    def finalize_run(
        self,
        *,
        output: Any = None,
        extra_context: Optional[Dict[str, Any]] = None,
        artifact_path: Optional[Union[str, Path]] = None,
        execution_error: Optional[BaseException] = None,
    ) -> RunVerdict:
        if self._finalized_verdict is not None and artifact_path is None:
            return self._finalized_verdict

        if isinstance(execution_error, PostconditionError) and self._postcondition_failure is None:
            self._postcondition_failure = execution_error
            self._record_failed_event(
                clause=f"contract.postconditions.{execution_error.postcondition.name}",
                evidence={"check": execution_error.postcondition.check},
                severity=execution_error.postcondition.severity,
            )
        if isinstance(execution_error, ContractViolation):
            self._blocked = True

        candidate_output = self._last_output if output is None else output
        if candidate_output is not None and not self._postconditions_evaluated:
            try:
                self.evaluate_postconditions(candidate_output, extra_context=extra_context)
            except PostconditionError:
                pass

        required_check_failure = any(
            check.required and check.status in {"fail", "blocked"}
            for check in self._checks.values()
        )
        warning_present = any(check.status == "warn" for check in self._checks.values()) or bool(
            self._warnings
        )
        unexpected_error = (
            execution_error is not None
            and not isinstance(execution_error, (ContractViolation, PostconditionError))
        )

        if self._blocked:
            outcome: Literal["pass", "warn", "blocked", "fail"] = "blocked"
            final_gate: Literal["allowed", "blocked", "failed"] = "blocked"
        elif self._postcondition_failure is not None or required_check_failure or unexpected_error:
            outcome = "fail"
            final_gate = "failed"
        elif warning_present:
            outcome = "warn"
            final_gate = "allowed"
        else:
            outcome = "pass"
            final_gate = "allowed"

        self._artifact_path = self._resolved_artifact_path(artifact_path)
        timestamp = datetime.now(timezone.utc).isoformat()
        contract_path = self._contract.source_path
        artifacts: Dict[str, Any] = {"verdict_path": str(self._artifact_path)}
        if contract_path is not None:
            artifacts["contract_path"] = contract_path

        verdict = RunVerdict(
            run_id=self._run_id,
            contract={
                "name": self._contract.identity.name,
                "version": self._contract.identity.version,
                "spec_version": self._contract.spec_version,
            },
            host={"name": self._host_name, "version": self._host_version},
            outcome=outcome,
            final_gate=final_gate,
            violations=[event.to_dict() for event in self.violations],
            checks=self.checks,
            budgets=self._snapshot_budgets(),
            artifacts=artifacts,
            timestamp=timestamp,
            warnings=self.warnings,
        )
        verdict.write_json(self._artifact_path)
        self._finalized_verdict = verdict
        return verdict

    def __enter__(self) -> "ContractEnforcer":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._finalized_verdict is None:
            self.finalize_run(execution_error=exc_val)


def enforce_contract(
    source: Union[str, Path],
    *,
    violation_destination: str = "stdout",
    strict: bool = True,
) -> Callable[[F], F]:
    """Decorator that wraps a function with contract enforcement."""
    contract = load_contract(source, strict=strict)

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            enforcer = ContractEnforcer(
                contract, violation_destination=violation_destination
            )
            sig = inspect.signature(fn)
            if "_enforcer" in sig.parameters or any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in sig.parameters.values()
            ):
                kwargs["_enforcer"] = enforcer

            try:
                if args and contract.input_schema is not None:
                    errors = enforcer.validate_input(args[0])
                    if errors:
                        enforcer._blocked = True
                        raise ContractViolation(f"Input validation failed: {errors}")

                if args and contract.preconditions:
                    enforcer.check_preconditions(args[0])

                result = fn(*args, **kwargs)

                if contract.output_schema is not None:
                    enforcer.validate_output(result)

                enforcer.evaluate_postconditions(result)
                enforcer.finalize_run(output=result)
                return result
            except Exception as exc:
                enforcer.finalize_run(execution_error=exc)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
