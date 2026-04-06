"""Tests for budget enforcement."""

from __future__ import annotations

import threading
import time

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
            tracker.record_shell_command()
        tracker.check_all()

    def test_cost_limit(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_cost_usd=1.00))
        tracker.add_cost(0.50)
        tracker.add_cost(0.40)
        with pytest.raises(BudgetExceededError, match="cost_usd"):
            tracker.add_cost(0.20)

    def test_token_limit(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_tokens=1000))
        tracker.add_tokens(800)
        with pytest.raises(BudgetExceededError, match="tokens"):
            tracker.add_tokens(300)

    def test_tool_call_limit(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_tool_calls=3))
        tracker.record_tool_call()
        tracker.record_tool_call()
        tracker.record_tool_call()
        with pytest.raises(BudgetExceededError, match="tool_calls"):
            tracker.record_tool_call()

    def test_shell_command_limit(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_shell_commands=1))
        tracker.record_shell_command()
        with pytest.raises(BudgetExceededError, match="shell_commands"):
            tracker.record_shell_command()

    def test_duration_limit(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_duration_seconds=0.01))
        time.sleep(0.02)
        with pytest.raises(BudgetExceededError, match="duration_seconds"):
            tracker.check_duration()

    def test_snapshot(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_cost_usd=10.0))
        tracker.add_cost(1.50)
        tracker.add_tokens(500)
        tracker.record_tool_call()
        tracker.record_shell_command()
        snapshot = tracker.snapshot()
        assert snapshot.cost_usd == 1.50
        assert snapshot.tokens == 500
        assert snapshot.tool_calls == 1
        assert snapshot.shell_commands == 1
        assert snapshot.elapsed_seconds >= 0

    def test_cost_callback(self) -> None:
        cost_value = [0.0]

        def get_cost() -> float:
            return cost_value[0]

        tracker = BudgetTracker(ResourceBudgets(max_cost_usd=1.00), cost_callback=get_cost)
        cost_value[0] = 0.50
        tracker.check_all()
        cost_value[0] = 1.50
        with pytest.raises(BudgetExceededError, match="cost_usd"):
            tracker.check_all()

    def test_reset(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_tool_calls=5, max_shell_commands=5))
        for _ in range(4):
            tracker.record_tool_call()
            tracker.record_shell_command()
        tracker.reset()
        snapshot = tracker.snapshot()
        assert snapshot.tool_calls == 0
        assert snapshot.shell_commands == 0
        assert snapshot.cost_usd == 0.0

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            BudgetTracker().add_cost(-1.0)

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            BudgetTracker().add_tokens(-1)

    def test_thread_safety(self) -> None:
        tracker = BudgetTracker(ResourceBudgets(max_tool_calls=10_000))
        errors: list = []

        def call_many() -> None:
            try:
                for _ in range(1000):
                    tracker.record_tool_call()
            except BudgetExceededError:
                errors.append(True)

        threads = [threading.Thread(target=call_many) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert tracker.snapshot().tool_calls == 5000

    def test_budget_exceeded_error_fields(self) -> None:
        err = BudgetExceededError("cost_usd", 5.23, 5.00)
        assert err.budget_type == "cost_usd"
        assert err.current == 5.23
        assert err.limit == 5.00
