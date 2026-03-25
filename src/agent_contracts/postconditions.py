"""Postcondition evaluation with safe expression checking.

Supports three enforcement timings:
- sync_block: fails the invocation if postcondition is not met
- sync_warn: logs a warning but allows the invocation to proceed
- async_monitor: queues for asynchronous evaluation

Expression evaluator uses a restricted subset — NO eval() or exec().
Supports basic comparisons, membership tests, and type checks.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agent_contracts.types import PostconditionDef

# Safe operators for expression evaluation
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
    """Resolve a dotted path like 'output.status' against an object or dict."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def _parse_value(token: str) -> Any:
    """Parse a literal value token (string, number, bool, None, list)."""
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
    # Try list literal: ["a", "b"]
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
    return token  # Treat as identifier path


def _split_list_items(s: str) -> List[str]:
    """Split comma-separated items, respecting quoted strings."""
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


def evaluate_expression(check: str, context: Dict[str, Any]) -> bool:
    """Evaluate a CEL-like expression safely against a context dict.

    Supported forms:
    - "output is not None"
    - "output is None"
    - "output.status == \"resolved\""
    - "output.status in [\"resolved\", \"escalated\"]"
    - "output.status not in [\"failed\"]"
    - "len(output.items) > 0"
    - "output.score >= 0.8"
    - "true" / "false"

    Returns True if the check passes, False otherwise.
    """
    check = check.strip()

    if check in ("true", "True"):
        return True
    if check in ("false", "False"):
        return False

    # "X is not None"
    m = re.match(r"^(\S+)\s+is\s+not\s+None$", check)
    if m:
        val = _resolve_path(context, m.group(1))
        return val is not None

    # "X is None"
    m = re.match(r"^(\S+)\s+is\s+None$", check)
    if m:
        val = _resolve_path(context, m.group(1))
        return val is None

    # "X not in [...]"
    m = re.match(r"^(\S+)\s+not\s+in\s+(\[.+\])$", check)
    if m:
        val = _resolve_path(context, m.group(1))
        allowed = _parse_value(m.group(2))
        return val not in allowed

    # "X in [...]"
    m = re.match(r"^(\S+)\s+in\s+(\[.+\])$", check)
    if m:
        val = _resolve_path(context, m.group(1))
        allowed = _parse_value(m.group(2))
        return val in allowed

    # "len(X) op Y"
    m = re.match(r"^len\((\S+)\)\s*(==|!=|>=?|<=?)\s*(.+)$", check)
    if m:
        val = _resolve_path(context, m.group(1))
        if val is None:
            return False
        op_fn = _OPERATORS[m.group(2)]
        rhs = _parse_value(m.group(3))
        return bool(op_fn(len(val), rhs))

    # "X op Y" (comparison)
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

    # Fallback: treat as a path and check truthiness
    val = _resolve_path(context, check)
    return bool(val)


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
    """Evaluate all postconditions against an output.

    - sync_block: raises PostconditionError on failure
    - sync_warn: calls on_warn callback on failure
    - async_monitor: calls on_async callback (deferred evaluation)

    Returns list of results for all evaluated postconditions.
    """
    context: Dict[str, Any] = {"output": output}
    if extra_context:
        context.update(extra_context)

    results: List[PostconditionResult] = []

    for pc in postconditions:
        if pc.enforcement == "async_monitor":
            if on_async:
                on_async(pc, output)
            results.append(PostconditionResult(postcondition=pc, passed=True, enforcement="async_monitor"))
            continue

        # Skip eval:judge checks — they require external LLM call
        if pc.check.startswith("eval:"):
            results.append(PostconditionResult(postcondition=pc, passed=True, enforcement=pc.enforcement))
            continue

        passed = evaluate_expression(pc.check, context)
        results.append(PostconditionResult(postcondition=pc, passed=passed, enforcement=pc.enforcement))

        if not passed:
            if pc.enforcement == "sync_block":
                raise PostconditionError(pc, output)
            elif pc.enforcement == "sync_warn" and on_warn:
                on_warn(pc, output)

    return results
