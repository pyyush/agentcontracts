"""Effect authorization — default-deny tool gating with glob pattern matching.

Authorized effects compose via intersection during delegation.
Declared effects compose via union for auditing.
Runtime enforces: declared ⊆ authorized.
"""

from __future__ import annotations

import fnmatch
from typing import List, Optional, Set

from agent_contracts.types import EffectsAuthorized, EffectsDeclared


class EffectDeniedError(Exception):
    """Raised when a tool call or effect is not authorized."""

    def __init__(self, effect_type: str, name: str, allowed: List[str]) -> None:
        self.effect_type = effect_type
        self.name = name
        self.allowed = allowed
        super().__init__(
            f"{effect_type} '{name}' denied. "
            f"Authorized: {allowed if allowed else '(none — default deny)'}"
        )


def _matches_any(name: str, patterns: List[str]) -> bool:
    """Check if a name matches any of the given glob patterns."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


class EffectGuard:
    """Enforces the effects.authorized allowlist (default-deny).

    All checks are O(n) where n = number of patterns. For production
    workloads with large allowlists, consider pre-compiling patterns.
    """

    def __init__(self, authorized: Optional[EffectsAuthorized] = None) -> None:
        self._authorized = authorized

    @property
    def is_configured(self) -> bool:
        """Whether effect authorization is configured."""
        return self._authorized is not None

    def check_tool(self, tool_name: str) -> bool:
        """Check if a tool call is authorized. Returns True if allowed."""
        if self._authorized is None:
            return True  # No authorization configured = allow all
        return _matches_any(tool_name, self._authorized.tools)

    def check_network(self, url: str) -> bool:
        """Check if a network request is authorized."""
        if self._authorized is None:
            return True
        return _matches_any(url, self._authorized.network)

    def check_state_write(self, scope: str) -> bool:
        """Check if a state write is authorized."""
        if self._authorized is None:
            return True
        return _matches_any(scope, self._authorized.state_writes)

    def require_tool(self, tool_name: str) -> None:
        """Assert a tool call is authorized; raise EffectDeniedError if not."""
        if not self.check_tool(tool_name):
            raise EffectDeniedError(
                "tool",
                tool_name,
                self._authorized.tools if self._authorized else [],
            )

    def require_network(self, url: str) -> None:
        """Assert a network request is authorized."""
        if not self.check_network(url):
            raise EffectDeniedError(
                "network",
                url,
                self._authorized.network if self._authorized else [],
            )

    def require_state_write(self, scope: str) -> None:
        """Assert a state write is authorized."""
        if not self.check_state_write(scope):
            raise EffectDeniedError(
                "state_write",
                scope,
                self._authorized.state_writes if self._authorized else [],
            )


def intersect_authorized(
    parent: EffectsAuthorized, child: EffectsAuthorized
) -> EffectsAuthorized:
    """Compute intersection of authorized effects (capability attenuation for delegation).

    The child can only use effects that BOTH parent and child authorize.
    Uses glob matching: a child pattern is kept only if it matches at least
    one parent pattern, or vice versa.
    """

    def _intersect_lists(parent_list: List[str], child_list: List[str]) -> List[str]:
        result: List[str] = []
        for c in child_list:
            if _matches_any(c, parent_list) or any(
                fnmatch.fnmatch(p, c) for p in parent_list
            ):
                result.append(c)
        return result

    return EffectsAuthorized(
        tools=_intersect_lists(parent.tools, child.tools),
        network=_intersect_lists(parent.network, child.network),
        state_writes=_intersect_lists(parent.state_writes, child.state_writes),
    )


def union_declared(a: EffectsDeclared, b: EffectsDeclared) -> EffectsDeclared:
    """Compute union of declared effects (footprint accumulation for auditing)."""

    def _union_unique(x: List[str], y: List[str]) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for item in x + y:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    return EffectsDeclared(
        tools=_union_unique(a.tools, b.tools),
        network=_union_unique(a.network, b.network),
        state_writes=_union_unique(a.state_writes, b.state_writes),
    )


def validate_declared_subset(
    declared: EffectsDeclared, authorized: EffectsAuthorized
) -> List[str]:
    """Validate that declared effects are a subset of authorized effects.

    Returns a list of violation messages. Empty = valid.
    """
    violations: List[str] = []
    for tool in declared.tools:
        if not _matches_any(tool, authorized.tools):
            violations.append(f"Declared tool '{tool}' not in authorized tools.")
    for url in declared.network:
        if not _matches_any(url, authorized.network):
            violations.append(f"Declared network '{url}' not in authorized network.")
    for scope in declared.state_writes:
        if not _matches_any(scope, authorized.state_writes):
            violations.append(
                f"Declared state_write '{scope}' not in authorized state_writes."
            )
    return violations
