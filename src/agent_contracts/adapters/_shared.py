"""Shared helpers for host adapter verdict behavior."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, Optional, Union

from agent_contracts.enforcer import ContractEnforcer, RunVerdict


class AdapterVerdictError(Exception):
    """Raised when an adapter-observed run finalizes to a non-green verdict."""

    def __init__(self, verdict: RunVerdict) -> None:
        checks = ", ".join(
            f"{check.name}={check.status}" for check in verdict.checks if check.status != "pass"
        )
        detail = f"; checks: {checks}" if checks else ""
        super().__init__(f"Adapter run finalized with outcome={verdict.outcome}{detail}")
        self.verdict = verdict


def installed_package_version(package_name: str) -> Optional[str]:
    """Return the installed distribution version for an optional SDK package."""
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _record_output_schema_failure(enforcer: ContractEnforcer, output: Any) -> None:
    errors = enforcer.validate_output(output)
    if not errors:
        return
    enforcer.record_check(
        "adapter.output_schema",
        "fail",
        required=True,
        detail="Adapter-observed output did not match contract.outputs.schema.",
        evidence={"errors": errors},
    )


def finalize_adapter_run(
    enforcer: ContractEnforcer,
    *,
    adapter_name: str,
    observed_completion: bool,
    output: Any = None,
    extra_context: Optional[Dict[str, Any]] = None,
    artifact_path: Optional[Union[str, Path]] = None,
    execution_error: Optional[BaseException] = None,
    validate_output: bool = True,
) -> RunVerdict:
    """Finalize a run without letting partially observed runs pass silently."""
    if enforcer.finalized_verdict is None:
        if output is not None and validate_output:
            _record_output_schema_failure(enforcer, output)
        elif output is None and execution_error is None:
            if observed_completion:
                enforcer.record_check(
                    "adapter.output_observed",
                    "fail",
                    required=True,
                    detail=(
                        f"{adapter_name} observed host completion but no output was "
                        "provided for output-schema or postcondition evaluation."
                    ),
                )
            else:
                enforcer.record_check(
                    "adapter.observed_completion",
                    "fail",
                    required=True,
                    detail=(
                        f"{adapter_name} verdict finalization happened before the "
                        "adapter observed host completion."
                    ),
                )

    return enforcer.finalize_run(
        output=output,
        extra_context=extra_context,
        artifact_path=artifact_path,
        execution_error=execution_error,
    )


def raise_if_blocking_verdict(verdict: RunVerdict, *, enabled: bool) -> None:
    """Raise for failed or blocked final verdicts when strict adapter mode is enabled."""
    if enabled and verdict.outcome in {"blocked", "fail"}:
        raise AdapterVerdictError(verdict)


def check_observed_effect(
    enforcer: ContractEnforcer,
    *,
    tool_name: str,
    tool_input: Any,
) -> bool:
    """Check a host-observed native coding effect when the payload is inspectable.

    Returns True when the tool name and payload mapped to a file, shell, or network
    surface. Returns False when the adapter should treat the call as a generic tool.
    """
    normalized = tool_name.replace("-", "_").lower()
    payload = tool_input if isinstance(tool_input, dict) else {"input": tool_input}

    if normalized in {"bash", "shell", "terminal", "run_shell", "shell_command"}:
        command = _first_string(payload, ("command", "cmd", "input"))
        if command is None:
            return False
        enforcer.check_shell_command(command)
        return True

    if normalized in {"read", "read_file", "file_read"}:
        path = _first_string(payload, ("file_path", "path", "input"))
        if path is None:
            return False
        enforcer.check_file_read(path)
        return True

    if normalized in {"write", "edit", "multiedit", "notebookedit", "write_file", "file_write"}:
        path = _first_string(payload, ("file_path", "path", "input"))
        if path is None:
            return False
        enforcer.check_file_write(path)
        return True

    if normalized in {"webfetch", "web_fetch", "fetch", "http_get", "requests_get"}:
        url = _first_string(payload, ("url", "uri", "input"))
        if url is None:
            return False
        enforcer.check_network_request(url)
        return True

    return False


def _first_string(payload: Dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None
