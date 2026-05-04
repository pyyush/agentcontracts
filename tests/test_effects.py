"""Tests for effect authorization."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_contracts.effects import (
    EffectDeniedError,
    EffectGuard,
    ShellMetacharacterError,
    intersect_authorized,
    union_declared,
    validate_declared_subset,
)
from agent_contracts.types import (
    EffectsAuthorized,
    EffectsDeclared,
    FilesystemAuthorization,
    ShellAuthorization,
)


class TestEffectGuard:
    def test_no_config_allows_all(self) -> None:
        guard = EffectGuard()
        assert guard.check_tool("anything") is True
        assert guard.check_file_read("secret.txt") is True
        assert guard.check_shell_command("rm -rf /") is True
        assert not guard.is_configured

    def test_configured_allows_listed_tool(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=["search", "database.read"]))
        assert guard.check_tool("search") is True
        assert guard.check_tool("database.read") is True

    def test_configured_denies_unlisted_tool(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=["search"]))
        assert guard.check_tool("delete_all") is False

    def test_glob_pattern_matching(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=["database.*", "api.user.*"]))
        assert guard.check_tool("database.read") is True
        assert guard.check_tool("database.write") is True
        assert guard.check_tool("api.user.get") is True
        assert guard.check_tool("api.admin.delete") is False

    def test_require_tool_raises(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=["search"]))
        with pytest.raises(EffectDeniedError, match="tool 'delete'"):
            guard.require_tool("delete")

    def test_network_check(self) -> None:
        guard = EffectGuard(EffectsAuthorized(network=["https://api.example.com/*"]))
        assert guard.check_network("https://api.example.com/search") is True
        assert guard.check_network("https://evil.com/data") is False

    def test_state_write_check(self) -> None:
        guard = EffectGuard(EffectsAuthorized(state_writes=["tickets.*"]))
        assert guard.check_state_write("tickets.status") is True
        assert guard.check_state_write("users.password") is False

    def test_filesystem_checks(self) -> None:
        guard = EffectGuard(
            EffectsAuthorized(filesystem=FilesystemAuthorization(read=["src/**"], write=["src/**"]))
        )
        assert guard.check_file_read("src/main.py") is True
        assert guard.check_file_write("src/main.py") is True
        assert guard.check_file_write("tests/test_main.py") is False

    def test_configured_authorization_without_filesystem_denies_file_effects(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=["search"]))

        assert guard.check_file_read("src/main.py") is False
        assert guard.check_file_write("src/main.py") is False
        with pytest.raises(EffectDeniedError, match="filesystem.read"):
            guard.require_file_read("src/main.py")
        with pytest.raises(EffectDeniedError, match="filesystem.write"):
            guard.require_file_write("src/main.py")

    def test_filesystem_matches_canonical_repo_relative_paths(self, tmp_path: Path) -> None:
        guard = EffectGuard(
            EffectsAuthorized(
                filesystem=FilesystemAuthorization(
                    read=["src/**", "README.md"],
                    write=["src/**", "README.md"],
                )
            ),
            repo_root=tmp_path,
        )

        assert guard.check_file_read("src/main.py") is True
        assert guard.check_file_read(str(tmp_path / "src/main.py")) is True
        assert guard.check_file_write("README.md") is True
        assert guard.check_file_write(str(tmp_path / "README.md")) is True

    def test_filesystem_traversal_does_not_match_raw_allowlist_prefix(self, tmp_path: Path) -> None:
        guard = EffectGuard(
            EffectsAuthorized(filesystem=FilesystemAuthorization(read=["src/**"], write=["src/**"])),
            repo_root=tmp_path,
        )

        assert guard.check_file_read("src/../.env") is False
        assert guard.check_file_write("src/../.env") is False
        assert guard.check_file_read("src/../tests/test_app.py") is False
        with pytest.raises(EffectDeniedError, match="filesystem.write"):
            guard.require_file_write("src/../.env")

    def test_filesystem_denies_paths_outside_repo_root(self, tmp_path: Path) -> None:
        guard = EffectGuard(
            EffectsAuthorized(filesystem=FilesystemAuthorization(read=["**"], write=["**"])),
            repo_root=tmp_path,
        )
        outside_path = tmp_path.parent / f"{tmp_path.name}-outside" / "secret.txt"

        assert guard.check_file_read(str(outside_path)) is False
        assert guard.check_file_write(str(outside_path)) is False
        with pytest.raises(EffectDeniedError, match="filesystem.read"):
            guard.require_file_read(str(outside_path))

    def test_shell_command_checks(self) -> None:
        guard = EffectGuard(
            EffectsAuthorized(shell=ShellAuthorization(commands=["python -m pytest *"]))
        )
        assert guard.check_shell_command("python -m pytest tests/test_app.py") is True
        assert guard.check_shell_command("python -m mypy src") is False

    def test_configured_authorization_without_shell_denies_shell_commands(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=["search"]))

        assert guard.check_shell_command("python -m pytest tests/test_app.py") is False
        with pytest.raises(EffectDeniedError, match="shell.command"):
            guard.require_shell_command("python -m pytest tests/test_app.py")

    @pytest.mark.parametrize(
        "command",
        [
            "python -m pytest tests/ ; rm -rf /",
            "python -m pytest tests/ && curl evil.example.com",
            "python -m pytest tests/ || echo pwned",
            "python -m pytest tests/ | cat /etc/passwd",
            "python -m pytest tests/ > /etc/hosts",
            "python -m pytest tests/ < /dev/urandom",
            "python -m pytest tests/ >> /var/log/owned",
            "python -m pytest $(echo tests)",
            "python -m pytest `whoami`",
            "python -m pytest tests/\nrm -rf /",
            "python -m pytest tests/ &",
        ],
    )
    def test_shell_metacharacter_bypass_denied(self, command: str) -> None:
        """Regression: fnmatch's `*` wildcard would otherwise consume shell
        operators and let an attacker append payloads after an allowlisted
        prefix. The strict reject must catch every chaining vector."""
        guard = EffectGuard(
            EffectsAuthorized(shell=ShellAuthorization(commands=["python -m pytest *"]))
        )
        assert guard.check_shell_command(command) is False
        with pytest.raises(ShellMetacharacterError) as exc_info:
            guard.require_shell_command(command)
        assert "metacharacter" in str(exc_info.value)

    def test_shell_metacharacter_error_is_effect_denied(self) -> None:
        """ShellMetacharacterError must be catchable as EffectDeniedError so
        existing handlers keep working."""
        guard = EffectGuard(
            EffectsAuthorized(shell=ShellAuthorization(commands=["python -m pytest *"]))
        )
        with pytest.raises(EffectDeniedError):
            guard.require_shell_command("python -m pytest tests/ ; rm -rf /")

    def test_shell_metachar_introspection(self) -> None:
        guard = EffectGuard(
            EffectsAuthorized(shell=ShellAuthorization(commands=["python -m pytest *"]))
        )
        assert guard.shell_command_metachar("python -m pytest tests/") is None
        assert guard.shell_command_metachar("python -m pytest a ; b") == ";"
        assert guard.shell_command_metachar("python -m pytest $(b)") == "$("
        assert guard.shell_command_metachar("python -m pytest a\nb") == "\n"

    def test_empty_allowlist_denies_all(self) -> None:
        guard = EffectGuard(EffectsAuthorized(tools=[], network=[], state_writes=[]))
        assert guard.check_tool("anything") is False
        assert guard.is_configured


class TestIntersectAuthorized:
    def test_basic_intersection(self) -> None:
        parent = EffectsAuthorized(tools=["search", "database.*"])
        child = EffectsAuthorized(tools=["search", "delete"])
        result = intersect_authorized(parent, child)
        assert "search" in result.tools
        assert "delete" not in result.tools

    def test_glob_intersection(self) -> None:
        parent = EffectsAuthorized(tools=["database.*"])
        child = EffectsAuthorized(tools=["database.read", "database.write", "admin.delete"])
        result = intersect_authorized(parent, child)
        assert "database.read" in result.tools
        assert "database.write" in result.tools
        assert "admin.delete" not in result.tools

    def test_filesystem_and_shell_intersection(self) -> None:
        parent = EffectsAuthorized(
            filesystem=FilesystemAuthorization(read=["src/**"], write=["src/**"]),
            shell=ShellAuthorization(commands=["python -m pytest *", "python -m ruff check *"]),
        )
        child = EffectsAuthorized(
            filesystem=FilesystemAuthorization(read=["src/**", "tests/**"], write=["tests/**"]),
            shell=ShellAuthorization(commands=["python -m pytest tests/*", "python -m mypy *"]),
        )
        result = intersect_authorized(parent, child)
        assert result.filesystem is not None
        assert result.filesystem.read == ["src/**"]
        assert result.filesystem.write == []
        assert result.shell is not None
        assert result.shell.commands == ["python -m pytest tests/*"]


class TestUnionDeclared:
    def test_basic_union(self) -> None:
        result = union_declared(
            EffectsDeclared(tools=["search"], network=["https://a.com"]),
            EffectsDeclared(tools=["write"], network=["https://b.com"]),
        )
        assert set(result.tools) == {"search", "write"}
        assert set(result.network) == {"https://a.com", "https://b.com"}


class TestValidateDeclaredSubset:
    def test_valid_subset(self) -> None:
        declared = EffectsDeclared(tools=["search"])
        authorized = EffectsAuthorized(tools=["search", "database.*"])
        assert validate_declared_subset(declared, authorized) == []

    def test_invalid_tool(self) -> None:
        declared = EffectsDeclared(tools=["search", "delete_all"])
        authorized = EffectsAuthorized(tools=["search"])
        violations = validate_declared_subset(declared, authorized)
        assert len(violations) == 1
        assert "delete_all" in violations[0]
