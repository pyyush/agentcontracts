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

# Shell metacharacters that enable command chaining, redirection, or
# substitution. Any command containing one of these is rejected outright
# in v0.2.x, regardless of pattern match. The fail-closed contract has
# no safe way to express "this prefix is allowed but only without an
# appended `; rm -rf /`" using fnmatch globs, because `*` would consume
# the operator and the payload as ordinary characters.
#
# v0.3.x will introduce a shlex-based token matcher that can express
# richer command shapes safely; until then, strict reject is the only
# correct fail-closed behavior.
_SHELL_METACHARS = frozenset(";&|<>`\n")
_SHELL_METASEQUENCES = ("$(",)


def _shell_metachar_in(command: str) -> Optional[str]:
    """Return the first shell metacharacter found, or None."""
    for ch in command:
        if ch in _SHELL_METACHARS:
            return ch
    for seq in _SHELL_METASEQUENCES:
        if seq in command:
            return seq
    return None


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


class ShellMetacharacterError(EffectDeniedError):
    """Raised when a shell command contains a chaining/redirection/
    substitution metacharacter. Distinct from a plain authorization
    failure so callers and verdict artifacts can distinguish 'matched
    no allowlist entry' from 'attempted to chain commands'."""

    def __init__(self, command: str, metachar: str, allowed: Sequence[str]) -> None:
        self.metachar = metachar
        self.command = command
        super().__init__(
            "shell.command",
            command,
            allowed,
        )
        # Override the message to surface the bypass attempt explicitly.
        self.args = (
            f"shell.command '{command}' rejected: contains shell metacharacter "
            f"'{metachar}'. Command chaining, redirection, and substitution are "
            f"not permitted under v0.2.x effect authorization. "
            f"Authorized patterns: {list(allowed) if allowed else '(none)'}",
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

    def _repo_relative_path(self, path: str) -> Optional[str]:
        raw = Path(path)
        absolute = raw if raw.is_absolute() else (self._repo_root / raw)
        absolute = absolute.resolve()
        try:
            return absolute.relative_to(self._repo_root).as_posix()
        except ValueError:
            return None

    def _filesystem_matches(self, path: str, patterns: Sequence[str]) -> bool:
        relative_path = self._repo_relative_path(path)
        if relative_path is None:
            return False
        return matches_any(relative_path, patterns)

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
        # Strict reject: any chaining/redirection/substitution metachar
        # bypasses fnmatch's `*` and would let an attacker append payloads
        # after an allowlisted prefix. Scan the RAW command (not the
        # whitespace-normalized form) so newlines are not lost.
        if _shell_metachar_in(command) is not None:
            return False
        normalized = self._normalized_command(command)
        return matches_any(normalized, self._authorized.shell.commands)

    def shell_command_metachar(self, command: str) -> Optional[str]:
        """Return the first shell metacharacter in the command, or None.
        Exposed so callers can distinguish 'unauthorized' from 'rejected
        as a chaining attempt' when constructing verdicts."""
        return _shell_metachar_in(command)

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
            allowed: List[str] = []
            if self._authorized is not None and self._authorized.shell is not None:
                allowed = list(self._authorized.shell.commands)
            metachar = _shell_metachar_in(command)
            normalized = self._normalized_command(command)
            if metachar is not None:
                raise ShellMetacharacterError(normalized, metachar, allowed)
            raise EffectDeniedError("shell.command", normalized, allowed)


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
