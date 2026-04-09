"""Tests for LangChain adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from agent_contracts.adapters.langchain import ContractCallbackHandler
from agent_contracts.enforcer import ContractViolation


@pytest.fixture
def handler(tmp_path: Path, tier1_data: Dict[str, Any]) -> ContractCallbackHandler:
    p = tmp_path / "contract.yaml"
    p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
    return ContractCallbackHandler.from_file(
        p, violation_destination="callback", raise_on_violation=True
    )


class TestContractCallbackHandler:
    def test_from_file(self, handler) -> None:
        assert handler.enforcer is not None
        assert handler.enforcer.contract.tier == 1

    def test_authorized_tool_passes(self, handler) -> None:
        handler.on_tool_start({"name": "search"}, "query")

    def test_unauthorized_tool_raises(self, handler) -> None:
        with pytest.raises(ContractViolation, match="not authorized"):
            handler.on_tool_start({"name": "delete_all"}, "query")

    def test_tool_budget_tracking(self, tmp_path, tier1_data) -> None:
        tier1_data["resources"]["budgets"]["max_tool_calls"] = 2
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
        h = ContractCallbackHandler.from_file(p, raise_on_violation=True)
        h.on_tool_start({"name": "search"}, "q1")
        h.on_tool_start({"name": "database.read"}, "q2")
        with pytest.raises(ContractViolation):
            h.on_tool_start({"name": "search"}, "q3")

    def test_violations_accumulated(self, handler) -> None:
        try:
            handler.on_tool_start({"name": "bad_tool"}, "q")
        except ContractViolation:
            pass
        assert len(handler.violations) == 1

    def test_non_raising_mode(self, tmp_path, tier1_data) -> None:
        p = tmp_path / "contract.yaml"
        p.write_text(yaml.dump(tier1_data, sort_keys=False), encoding="utf-8")
        h = ContractCallbackHandler.from_file(p, raise_on_violation=False)
        h.on_tool_start({"name": "unauthorized"}, "q")  # Should not raise

    def test_chain_end_postconditions(self, handler) -> None:
        handler.on_chain_end({"result": "something"})  # Should pass

    def test_on_tool_end(self, handler) -> None:
        handler.on_tool_end("result")  # No-op, should not raise


class TestRealSDKIntegration:
    """Verifies the adapter is a real subclass of the installed
    langchain-core BaseCallbackHandler. Skipped if langchain-core absent."""

    def test_subclass_of_real_base_callback_handler(self, handler) -> None:
        callbacks = pytest.importorskip("langchain_core.callbacks")
        assert isinstance(handler, callbacks.BaseCallbackHandler)

    def test_hook_method_signatures_present(self) -> None:
        callbacks = pytest.importorskip("langchain_core.callbacks")
        for name in ("on_tool_start", "on_tool_end", "on_chain_end", "on_llm_end"):
            assert hasattr(callbacks.BaseCallbackHandler, name), f"SDK missing {name}"
            assert hasattr(ContractCallbackHandler, name), f"adapter missing {name}"
