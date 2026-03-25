"""Tests for effect authorization."""

from __future__ import annotations

import pytest

from agent_contracts.effects import (
    EffectDeniedError,
    EffectGuard,
    intersect_authorized,
    union_declared,
    validate_declared_subset,
)
from agent_contracts.types import EffectsAuthorized, EffectsDeclared


class TestEffectGuard:
    def test_no_config_allows_all(self) -> None:
        guard = EffectGuard()
        assert guard.check_tool("anything") is True
        assert not guard.is_configured

    def test_configured_allows_listed_tool(self) -> None:
        auth = EffectsAuthorized(tools=["search", "database.read"])
        guard = EffectGuard(auth)
        assert guard.check_tool("search") is True
        assert guard.check_tool("database.read") is True

    def test_configured_denies_unlisted_tool(self) -> None:
        auth = EffectsAuthorized(tools=["search"])
        guard = EffectGuard(auth)
        assert guard.check_tool("delete_all") is False

    def test_glob_pattern_matching(self) -> None:
        auth = EffectsAuthorized(tools=["database.*", "api.user.*"])
        guard = EffectGuard(auth)
        assert guard.check_tool("database.read") is True
        assert guard.check_tool("database.write") is True
        assert guard.check_tool("api.user.get") is True
        assert guard.check_tool("api.admin.delete") is False

    def test_require_tool_raises(self) -> None:
        auth = EffectsAuthorized(tools=["search"])
        guard = EffectGuard(auth)
        with pytest.raises(EffectDeniedError, match="tool 'delete'"):
            guard.require_tool("delete")

    def test_require_tool_passes(self) -> None:
        auth = EffectsAuthorized(tools=["search"])
        guard = EffectGuard(auth)
        guard.require_tool("search")  # Should not raise

    def test_network_check(self) -> None:
        auth = EffectsAuthorized(network=["https://api.example.com/*"])
        guard = EffectGuard(auth)
        assert guard.check_network("https://api.example.com/search") is True
        assert guard.check_network("https://evil.com/data") is False

    def test_state_write_check(self) -> None:
        auth = EffectsAuthorized(state_writes=["tickets.*"])
        guard = EffectGuard(auth)
        assert guard.check_state_write("tickets.status") is True
        assert guard.check_state_write("users.password") is False

    def test_empty_allowlist_denies_all(self) -> None:
        auth = EffectsAuthorized(tools=[], network=[], state_writes=[])
        guard = EffectGuard(auth)
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

    def test_empty_parent_denies_all(self) -> None:
        parent = EffectsAuthorized(tools=[])
        child = EffectsAuthorized(tools=["search", "read"])
        result = intersect_authorized(parent, child)
        assert result.tools == []


class TestUnionDeclared:
    def test_basic_union(self) -> None:
        a = EffectsDeclared(tools=["search"], network=["https://a.com"])
        b = EffectsDeclared(tools=["write"], network=["https://b.com"])
        result = union_declared(a, b)
        assert set(result.tools) == {"search", "write"}
        assert set(result.network) == {"https://a.com", "https://b.com"}

    def test_deduplication(self) -> None:
        a = EffectsDeclared(tools=["search", "read"])
        b = EffectsDeclared(tools=["search", "write"])
        result = union_declared(a, b)
        assert result.tools == ["search", "read", "write"]


class TestValidateDeclaredSubset:
    def test_valid_subset(self) -> None:
        declared = EffectsDeclared(tools=["search"])
        authorized = EffectsAuthorized(tools=["search", "database.*"])
        violations = validate_declared_subset(declared, authorized)
        assert violations == []

    def test_invalid_tool(self) -> None:
        declared = EffectsDeclared(tools=["search", "delete_all"])
        authorized = EffectsAuthorized(tools=["search"])
        violations = validate_declared_subset(declared, authorized)
        assert len(violations) == 1
        assert "delete_all" in violations[0]

    def test_glob_matching(self) -> None:
        declared = EffectsDeclared(tools=["database.read"])
        authorized = EffectsAuthorized(tools=["database.*"])
        violations = validate_declared_subset(declared, authorized)
        assert violations == []
