"""Tests for budget enforcement."""

from __future__ import annotations

import threading

import pytest

from agent_contracts.budgets import BudgetExceededError, BudgetTracker
from agent_contracts.types import ResourceBudgets


class TestBudgetTracker:
    def test_no_config_allows_all(self) -> None:
        tracker = BudgetTracker()
        assert not tracker.is_configured
        tracker.add_cost(100.0)
        tracker.add_tokens(1_000_000)
        for _ in range(1000):
            tracker.record_tool_call()
        tracker.check_all()  # Should not raise

    def test_cost_limit(self) -> None:
        budgets = ResourceBudgets(max_cost_usd=1.00)
        tracker = BudgetTracker(budgets)
        tracker.add_cost(0.50)
        tracker.add_cost(0.40)
        with pytest.raises(BudgetExceededError, match="cost_usd"):
            tracker.add_cost(0.20)

    def test_token_limit(self) -> None:
        budgets = ResourceBudgets(max_tokens=1000)
        tracker = BudgetTracker(budgets)
        tracker.add_tokens(800)
        with pytest.raises(BudgetExceededError, match="tokens"):
            tracker.add_tokens(300)

    def test_tool_call_limit(self) -> None:
        budgets = ResourceBudgets(max_tool_calls=3)
        tracker = BudgetTracker(budgets)
        tracker.record_tool_call()
        tracker.record_tool_call()
        tracker.record_tool_call()
        with pytest.raises(BudgetExceededError, match="tool_calls"):
            tracker.record_tool_call()

    def test_duration_limit(self) -> None:
        budgets = ResourceBudgets(max_duration_seconds=0.01)
        tracker = BudgetTracker(budgets)
        import time

        time.sleep(0.02)
        with pytest.raises(BudgetExceededError, match="duration_seconds"):
            tracker.check_duration()

    def test_snapshot(self) -> None:
        budgets = ResourceBudgets(max_cost_usd=10.0)
        tracker = BudgetTracker(budgets)
        tracker.add_cost(1.50)
        tracker.add_tokens(500)
        tracker.record_tool_call()
        snap = tracker.snapshot()
        assert snap.cost_usd == 1.50
        assert snap.tokens == 500
        assert snap.tool_calls == 1
        assert snap.elapsed_seconds >= 0

    def test_cost_callback(self) -> None:
        cost_value = [0.0]

        def get_cost() -> float:
            return cost_value[0]

        budgets = ResourceBudgets(max_cost_usd=1.00)
        tracker = BudgetTracker(budgets, cost_callback=get_cost)
        cost_value[0] = 0.50
        tracker.check_all()  # OK
        cost_value[0] = 1.50
        with pytest.raises(BudgetExceededError, match="cost_usd"):
            tracker.check_all()

    def test_reset(self) -> None:
        budgets = ResourceBudgets(max_tool_calls=5)
        tracker = BudgetTracker(budgets)
        for _ in range(4):
            tracker.record_tool_call()
        tracker.reset()
        snap = tracker.snapshot()
        assert snap.tool_calls == 0
        assert snap.cost_usd == 0.0

    def test_negative_cost_rejected(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="non-negative"):
            tracker.add_cost(-1.0)

    def test_negative_tokens_rejected(self) -> None:
        tracker = BudgetTracker()
        with pytest.raises(ValueError, match="non-negative"):
            tracker.add_tokens(-1)

    def test_thread_safety(self) -> None:
        budgets = ResourceBudgets(max_tool_calls=10_000)
        tracker = BudgetTracker(budgets)
        errors: list = []

        def call_many() -> None:
            try:
                for _ in range(1000):
                    tracker.record_tool_call()
            except BudgetExceededError:
                errors.append(True)

        threads = [threading.Thread(target=call_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = tracker.snapshot()
        assert snap.tool_calls == 5000

    def test_budget_exceeded_error_fields(self) -> None:
        err = BudgetExceededError("cost_usd", 5.23, 5.00)
        assert err.budget_type == "cost_usd"
        assert err.current == 5.23
        assert err.limit == 5.00
