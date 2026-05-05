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

    def test_logical_and_or(self) -> None:
        ctx = {"checks": {"pytest": {"exit_code": 0}, "ruff": {"exit_code": 1}}}
        assert evaluate_expression("checks.pytest.exit_code == 0 and checks.ruff.exit_code == 1", ctx) is True
        assert evaluate_expression("checks.pytest.exit_code == 1 or checks.ruff.exit_code == 1", ctx) is True

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
        assert warnings == ["warn_check"]
        assert results[0].passed is False

    def test_eval_sync_block_without_evaluator_raises(self) -> None:
        pcs = [PostconditionDef(name="judge", check="eval:quality_judge", enforcement="sync_block")]
        with pytest.raises(PostconditionError, match="judge"):
            evaluate_postconditions(pcs, "anything")

    def test_eval_sync_block_with_evaluator_can_pass(self) -> None:
        pcs = [PostconditionDef(name="judge", check="eval:quality_judge", enforcement="sync_block")]
        results = evaluate_postconditions(
            pcs,
            "anything",
            eval_evaluator=lambda pc, output, context: output == "anything"
            and context["output"] == "anything"
            and pc.check == "eval:quality_judge",
        )
        assert results[0].passed is True

    def test_eval_sync_warn_without_evaluator_warns(self) -> None:
        warnings: list[str] = []
        pcs = [PostconditionDef(name="judge", check="eval:quality_judge", enforcement="sync_warn")]
        results = evaluate_postconditions(
            pcs,
            "anything",
            on_warn=lambda pc, output: warnings.append(pc.name),
        )
        assert warnings == ["judge"]
        assert results[0].passed is False

    def test_eval_async_monitor_without_evaluator_is_visible(self) -> None:
        async_checks: list[str] = []
        pcs = [
            PostconditionDef(
                name="judge",
                check="eval:quality_judge",
                enforcement="async_monitor",
            )
        ]
        results = evaluate_postconditions(
            pcs,
            "anything",
            on_async=lambda pc, output: async_checks.append(pc.name),
        )
        assert async_checks == ["judge"]
        assert results[0].passed is False

    def test_checks_context(self) -> None:
        pcs = [
            PostconditionDef(
                name="repo_checks_green",
                check="checks.pytest.exit_code == 0 and checks.ruff.exit_code == 0",
                enforcement="sync_block",
            )
        ]
        results = evaluate_postconditions(
            pcs,
            {"status": "done"},
            extra_context={"checks": {"pytest": {"exit_code": 0}, "ruff": {"exit_code": 0}}},
        )
        assert results[0].passed is True
