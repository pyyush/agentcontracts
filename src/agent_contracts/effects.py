"""Effect authorization for coding/build agents.

Authorized effects compose via intersection during delegation.
Declared effects compose via union for auditing.
Runtime enforces: declared ⊆ authorized.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List, Optional, Sequence, Set

from agent_contracts.types import (
    EffectsAuthorized,
    EffectsDeclared,
    FilesystemAuthorization,
    ShellAuthorization,
)


class EffectDeniedError(Exception):
    """Raised when a tool call or effect is not authorized."""

    def __init__(self, effect_type: str, name: str, allowed: Sequence[str]) -> None:
        self.effect_type = effect_type
        self.name = name
        self.allowed = list(allowed)
        super().__init__(
            f"{effect_type} '{name}' denied. "
            f"Authorized: {list(allowed) if allowed else '(none — default deny)'}"
        )


def matches_any(name: str, patterns: Sequence[str]) -> bool:
    """Check if a name matches any of the given glob patterns."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _intersect_lists(parent_list: Sequence[str], child_list: Sequence[str]) -> List[str]:
    result: List[str] = []
    for child_pattern in child_list:
        if matches_any(child_pattern, parent_list) or any(
            fnmatch.fnmatch(parent_pattern, child_pattern) for parent_pattern in parent_list
        ):
            result.append(child_pattern)
    return result


class EffectGuard:
    """Enforces the effects.authorized allowlist (default-deny when configured)."""

    def __init__(
        self,
        authorized: Optional[EffectsAuthorized] = None,
        *,
        repo_root: Optional[Path] = None,
    ) -> None:
        self._authorized = authorized
        self._repo_root = repo_root.resolve() if repo_root is not None else Path.cwd().resolve()

    @property
    def is_configured(self) -> bool:
        """Whether effect authorization was configured on the contract."""
        return self._authorized is not None

    def _path_candidates(self, path: str) -> List[str]:
        raw = Path(path)
        absolute = raw if raw.is_absolute() else (self._repo_root / raw)
        absolute = absolute.resolve()
        candidates: List[str] = [path, absolute.as_posix()]
        try:
            candidates.append(absolute.relative_to(self._repo_root).as_posix())
        except ValueError:
            pass
        return list(dict.fromkeys(candidates))

    def _filesystem_matches(self, path: str, patterns: Sequence[str]) -> bool:
        return any(matches_any(candidate, patterns) for candidate in self._path_candidates(path))

    def _normalized_command(self, command: str) -> str:
        return " ".join(command.strip().split())

    def check_tool(self, tool_name: str) -> bool:
        if self._authorized is None:
            return True
        return matches_any(tool_name, self._authorized.tools)

    def check_network(self, url: str) -> bool:
        if self._authorized is None:
            return True
        return matches_any(url, self._authorized.network)

    def check_state_write(self, scope: str) -> bool:
        if self._authorized is None:
            return True
        return matches_any(scope, self._authorized.state_writes)

    def check_file_read(self, path: str) -> bool:
        if self._authorized is None or self._authorized.filesystem is None:
            return True
        return self._filesystem_matches(path, self._authorized.filesystem.read)

    def check_file_write(self, path: str) -> bool:
        if self._authorized is None or self._authorized.filesystem is None:
            return True
        return self._filesystem_matches(path, self._authorized.filesystem.write)

    def check_shell_command(self, command: str) -> bool:
        if self._authorized is None or self._authorized.shell is None:
            return True
        normalized = self._normalized_command(command)
        return matches_any(normalized, self._authorized.shell.commands)

    def require_tool(self, tool_name: str) -> None:
        if not self.check_tool(tool_name):
            raise EffectDeniedError(
                "tool",
                tool_name,
                self._authorized.tools if self._authorized else [],
            )

    def require_network(self, url: str) -> None:
        if not self.check_network(url):
            raise EffectDeniedError(
                "network",
                url,
                self._authorized.network if self._authorized else [],
            )

    def require_state_write(self, scope: str) -> None:
        if not self.check_state_write(scope):
            raise EffectDeniedError(
                "state_write",
                scope,
                self._authorized.state_writes if self._authorized else [],
            )

    def require_file_read(self, path: str) -> None:
        if not self.check_file_read(path):
            allowed = []
            if self._authorized is not None and self._authorized.filesystem is not None:
                allowed = self._authorized.filesystem.read
            raise EffectDeniedError("filesystem.read", path, allowed)

    def require_file_write(self, path: str) -> None:
        if not self.check_file_write(path):
            allowed = []
            if self._authorized is not None and self._authorized.filesystem is not None:
                allowed = self._authorized.filesystem.write
            raise EffectDeniedError("filesystem.write", path, allowed)

    def require_shell_command(self, command: str) -> None:
        if not self.check_shell_command(command):
            allowed = []
            if self._authorized is not None and self._authorized.shell is not None:
                allowed = self._authorized.shell.commands
            raise EffectDeniedError("shell.command", self._normalized_command(command), allowed)


def intersect_authorized(parent: EffectsAuthorized, child: EffectsAuthorized) -> EffectsAuthorized:
    """Compute intersection of authorized effects (capability attenuation for delegation)."""

    filesystem: Optional[FilesystemAuthorization] = None
    if parent.filesystem is not None or child.filesystem is not None:
        parent_fs = parent.filesystem or FilesystemAuthorization()
        child_fs = child.filesystem or FilesystemAuthorization()
        filesystem = FilesystemAuthorization(
            read=_intersect_lists(parent_fs.read, child_fs.read),
            write=_intersect_lists(parent_fs.write, child_fs.write),
        )

    shell: Optional[ShellAuthorization] = None
    if parent.shell is not None or child.shell is not None:
        parent_shell = parent.shell or ShellAuthorization()
        child_shell = child.shell or ShellAuthorization()
        shell = ShellAuthorization(commands=_intersect_lists(parent_shell.commands, child_shell.commands))

    return EffectsAuthorized(
        tools=_intersect_lists(parent.tools, child.tools),
        network=_intersect_lists(parent.network, child.network),
        state_writes=_intersect_lists(parent.state_writes, child.state_writes),
        filesystem=filesystem,
        shell=shell,
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
    """Validate that declared effects are a subset of authorized effects."""
    violations: List[str] = []
    for tool in declared.tools:
        if not matches_any(tool, authorized.tools):
            violations.append(f"Declared tool '{tool}' not in authorized tools.")
    for url in declared.network:
        if not matches_any(url, authorized.network):
            violations.append(f"Declared network '{url}' not in authorized network.")
    for scope in declared.state_writes:
        if not matches_any(scope, authorized.state_writes):
            violations.append(
                f"Declared state_write '{scope}' not in authorized state_writes."
            )
    return violations
