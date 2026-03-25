"""Tests for postcondition evaluation."""

from __future__ import annotations

import pytest

from agent_contracts.postconditions import (
    PostconditionError,
    evaluate_expression,
    evaluate_postconditions,
)
from agent_contracts.types import PostconditionDef


class TestEvaluateExpression:
    def test_true_literal(self) -> None:
        assert evaluate_expression("true", {}) is True

    def test_false_literal(self) -> None:
        assert evaluate_expression("false", {}) is False

    def test_is_not_none(self) -> None:
        assert evaluate_expression("output is not None", {"output": "hello"}) is True
        assert evaluate_expression("output is not None", {"output": None}) is False

    def test_is_none(self) -> None:
        assert evaluate_expression("output is None", {"output": None}) is True
        assert evaluate_expression("output is None", {"output": "x"}) is False

    def test_equality(self) -> None:
        ctx = {"output": {"status": "resolved"}}
        assert evaluate_expression('output.status == "resolved"', ctx) is True
        assert evaluate_expression('output.status == "failed"', ctx) is False

    def test_inequality(self) -> None:
        ctx = {"output": {"status": "resolved"}}
        assert evaluate_expression('output.status != "failed"', ctx) is True

    def test_numeric_comparison(self) -> None:
        ctx = {"output": {"score": 0.85}}
        assert evaluate_expression("output.score >= 0.8", ctx) is True
        assert evaluate_expression("output.score > 0.9", ctx) is False

    def test_in_list(self) -> None:
        ctx = {"output": {"status": "resolved"}}
        assert evaluate_expression('output.status in ["resolved", "escalated"]', ctx) is True
        assert evaluate_expression('output.status in ["failed", "pending"]', ctx) is False

    def test_not_in_list(self) -> None:
        ctx = {"output": {"status": "resolved"}}
        assert evaluate_expression('output.status not in ["failed"]', ctx) is True

    def test_len_check(self) -> None:
        ctx = {"output": {"items": [1, 2, 3]}}
        assert evaluate_expression("len(output.items) > 0", ctx) is True
        assert evaluate_expression("len(output.items) == 3", ctx) is True

    def test_nested_path(self) -> None:
        ctx = {"output": {"data": {"nested": {"value": 42}}}}
        assert evaluate_expression("output.data.nested.value == 42", ctx) is True

    def test_missing_path_returns_false(self) -> None:
        ctx = {"output": {}}
        assert evaluate_expression("output.nonexistent is not None", ctx) is False

    def test_truthiness_fallback(self) -> None:
        assert evaluate_expression("output", {"output": "nonempty"}) is True
        assert evaluate_expression("output", {"output": ""}) is False


class TestEvaluatePostconditions:
    def test_sync_block_passes(self) -> None:
        pcs = [PostconditionDef(name="check", check="output is not None", enforcement="sync_block")]
        results = evaluate_postconditions(pcs, "hello")
        assert len(results) == 1
        assert results[0].passed is True

    def test_sync_block_raises(self) -> None:
        pcs = [PostconditionDef(name="check", check="output is not None", enforcement="sync_block")]
        with pytest.raises(PostconditionError, match="check"):
            evaluate_postconditions(pcs, None)

    def test_sync_warn_calls_callback(self) -> None:
        warnings: list = []
        pcs = [PostconditionDef(name="warn_check", check='output == "good"', enforcement="sync_warn")]
        results = evaluate_postconditions(pcs, "bad", on_warn=lambda pc, o: warnings.append(pc.name))
        assert len(warnings) == 1
        assert warnings[0] == "warn_check"
        assert results[0].passed is False

    def test_async_monitor_deferred(self) -> None:
        async_items: list = []
        pcs = [PostconditionDef(name="async_check", check="output > 0", enforcement="async_monitor")]
        results = evaluate_postconditions(pcs, -1, on_async=lambda pc, o: async_items.append(pc.name))
        assert len(async_items) == 1
        # async_monitor always returns passed=True (deferred evaluation)
        assert results[0].passed is True

    def test_eval_judge_skipped(self) -> None:
        pcs = [PostconditionDef(name="judge", check="eval:quality_judge", enforcement="sync_block")]
        results = evaluate_postconditions(pcs, "anything")
        assert results[0].passed is True  # Skipped, not evaluated

    def test_multiple_postconditions(self) -> None:
        pcs = [
            PostconditionDef(name="not_none", check="output is not None", enforcement="sync_block"),
            PostconditionDef(name="has_data", check='output.status == "ok"', enforcement="sync_warn"),
        ]
        results = evaluate_postconditions(pcs, {"status": "ok"})
        assert all(r.passed for r in results)
