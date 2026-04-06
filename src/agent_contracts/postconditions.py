"""Postcondition evaluation with safe expression checking.

Supports three enforcement timings:
- sync_block: fails the invocation if postcondition is not met
- sync_warn: logs a warning but allows the invocation to proceed
- async_monitor: queues for asynchronous evaluation

Expression evaluator uses a restricted subset — NO eval() or exec().
Supports basic comparisons, membership tests, length checks, and simple
boolean composition with `and` / `or`.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agent_contracts.types import PostconditionDef, PreconditionDef

_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


class PostconditionError(Exception):
    """Raised when a sync_block postcondition fails."""

    def __init__(self, postcondition: PostconditionDef, output: Any) -> None:
        self.postcondition = postcondition
        self.output = output
        super().__init__(
            f"Postcondition '{postcondition.name}' failed "
            f"(enforcement={postcondition.enforcement}, severity={postcondition.severity})"
        )


def _resolve_path(obj: Any, path: str) -> Any:
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def _parse_value(token: str) -> Any:
    token = token.strip()
    if token == "None" or token == "null":
        return None
    if token == "True" or token == "true":
        return True
    if token == "False" or token == "false":
        return False
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        items = [_parse_value(item.strip()) for item in _split_list_items(inner)]
        return items
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    return token


def _split_list_items(s: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    in_quote: Optional[str] = None
    for ch in s:
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        items.append("".join(current).strip())
    return items


def _split_logical(expr: str, operator_token: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    in_quote: Optional[str] = None
    i = 0
    while i < len(expr):
        ch = expr[i]
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
            i += 1
            continue
        if ch in "([":
            depth += 1
            current.append(ch)
            i += 1
            continue
        if ch in ")]":
            depth = max(0, depth - 1)
            current.append(ch)
            i += 1
            continue
        if depth == 0 and expr.startswith(operator_token, i):
            parts.append("".join(current).strip())
            current = []
            i += len(operator_token)
            continue
        current.append(ch)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return parts


def evaluate_expression(check: str, context: Dict[str, Any]) -> bool:
    check = check.strip()

    or_parts = _split_logical(check, " or ")
    if len(or_parts) > 1:
        return any(evaluate_expression(part, context) for part in or_parts)

    and_parts = _split_logical(check, " and ")
    if len(and_parts) > 1:
        return all(evaluate_expression(part, context) for part in and_parts)

    if check in ("true", "True"):
        return True
    if check in ("false", "False"):
        return False

    match = re.match(r"^(\S+)\s+is\s+not\s+None$", check)
    if match:
        val = _resolve_path(context, match.group(1))
        return val is not None

    match = re.match(r"^(\S+)\s+is\s+None$", check)
    if match:
        val = _resolve_path(context, match.group(1))
        return val is None

    match = re.match(r"^(\S+)\s+not\s+in\s+(\[.+\])$", check)
    if match:
        val = _resolve_path(context, match.group(1))
        allowed = _parse_value(match.group(2))
        return val not in allowed

    match = re.match(r"^(\S+)\s+in\s+(\[.+\])$", check)
    if match:
        val = _resolve_path(context, match.group(1))
        allowed = _parse_value(match.group(2))
        return val in allowed

    match = re.match(r"^len\((\S+)\)\s*(==|!=|>=?|<=?)\s*(.+)$", check)
    if match:
        val = _resolve_path(context, match.group(1))
        if val is None:
            return False
        op_fn = _OPERATORS[match.group(2)]
        rhs = _parse_value(match.group(3))
        return bool(op_fn(len(val), rhs))

    for op_str in (">=", "<=", "!=", "==", ">", "<"):
        parts = check.split(op_str, 1)
        if len(parts) == 2:
            lhs_token = parts[0].strip()
            rhs_token = parts[1].strip()
            lhs = _resolve_path(context, lhs_token)
            rhs = _parse_value(rhs_token)
            if isinstance(rhs, str) and not (
                rhs_token.startswith('"') or rhs_token.startswith("'")
            ):
                rhs = _resolve_path(context, rhs_token)
            op_fn = _OPERATORS[op_str]
            try:
                return bool(op_fn(lhs, rhs))
            except TypeError:
                return False

    val = _resolve_path(context, check)
    return bool(val)


class PreconditionError(Exception):
    """Raised when a precondition fails (input rejected before agent runs)."""

    def __init__(self, precondition: PreconditionDef, input_data: Any) -> None:
        self.precondition = precondition
        self.input_data = input_data
        super().__init__(
            f"Precondition '{precondition.name}' failed: {precondition.check}"
        )


@dataclass
class PreconditionResult:
    """Result of evaluating a precondition."""

    precondition: PreconditionDef
    passed: bool


def evaluate_preconditions(
    preconditions: List[PreconditionDef],
    input_data: Any,
    *,
    raise_on_failure: bool = True,
) -> List[PreconditionResult]:
    context: Dict[str, Any] = {"input": input_data}

    results: List[PreconditionResult] = []
    for pc in preconditions:
        passed = evaluate_expression(pc.check, context)
        results.append(PreconditionResult(precondition=pc, passed=passed))
        if not passed and raise_on_failure:
            raise PreconditionError(pc, input_data)

    return results


@dataclass
class PostconditionResult:
    """Result of evaluating a postcondition."""

    postcondition: PostconditionDef
    passed: bool
    enforcement: str


def evaluate_postconditions(
    postconditions: List[PostconditionDef],
    output: Any,
    *,
    extra_context: Optional[Dict[str, Any]] = None,
    on_warn: Optional[Callable[[PostconditionDef, Any], None]] = None,
    on_async: Optional[Callable[[PostconditionDef, Any], None]] = None,
) -> List[PostconditionResult]:
    context: Dict[str, Any] = {"output": output}
    if extra_context:
        context.update(extra_context)

    results: List[PostconditionResult] = []

    for pc in postconditions:
        if pc.enforcement == "async_monitor":
            if on_async:
                on_async(pc, output)
            results.append(
                PostconditionResult(postcondition=pc, passed=True, enforcement="async_monitor")
            )
            continue

        if pc.check.startswith("eval:"):
            results.append(
                PostconditionResult(postcondition=pc, passed=True, enforcement=pc.enforcement)
            )
            continue

        passed = evaluate_expression(pc.check, context)
        results.append(
            PostconditionResult(postcondition=pc, passed=passed, enforcement=pc.enforcement)
        )

        if not passed:
            if pc.enforcement == "sync_block":
                raise PostconditionError(pc, output)
            if pc.enforcement == "sync_warn" and on_warn:
                on_warn(pc, output)

    return results
