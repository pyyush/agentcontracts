"""Tests for Pydantic AI adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from agent_contracts.adapters.pydantic_ai import ContractMiddleware
from agent_contracts.enforcer import ContractViolation


@pytest.fixture
def middleware(tmp_path: Path, tier1_data: Dict[str, Any]) -> ContractMiddleware:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return ContractMiddleware.from_file(p, violation_destination="callback",
                                         violation_callback=lambda e: None)


class TestContractMiddleware:
    def test_from_file(self, middleware) -> None:
        assert middleware.enforcer is not None

    def test_check_authorized_tool(self, middleware) -> None:
        middleware.check_tool("search")

    def test_check_unauthorized_tool(self, middleware) -> None:
        with pytest.raises(ContractViolation):
            middleware.check_tool("evil_tool")

    def test_validate_result(self, middleware) -> None:
        errors = middleware.validate_result({"result": "ok"})
        assert errors == []

    def test_wrap_tool(self, middleware) -> None:
        def search(q: str) -> str:
            return f"found: {q}"

        wrapped = middleware.wrap_tool(search, "search")
        assert wrapped("test") == "found: test"

    def test_wrap_unauthorized_tool(self, middleware) -> None:
        def bad_tool() -> str:
            return "nope"

        wrapped = middleware.wrap_tool(bad_tool, "unauthorized")
        with pytest.raises(ContractViolation):
            wrapped()

    def test_violations_tracked(self, middleware) -> None:
        try:
            middleware.check_tool("bad")
        except ContractViolation:
            pass
        assert len(middleware.violations) == 1
