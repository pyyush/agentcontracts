"""Budget enforcement — per-invocation resource limits with circuit breaker.

Thread-safe counters for cost, tokens, tool calls, and elapsed time.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from agent_contracts.types import ResourceBudgets


class BudgetExceededError(Exception):
    """Raised when a budget threshold is exceeded."""

    def __init__(self, budget_type: str, current: float, limit: float) -> None:
        self.budget_type = budget_type
        self.current = current
        self.limit = limit
        super().__init__(
            f"Budget exceeded: {budget_type} = {current:.4g} (limit: {limit:.4g})"
        )


@dataclass
class BudgetSnapshot:
    """Point-in-time snapshot of budget consumption."""

    cost_usd: float = 0.0
    tokens: int = 0
    tool_calls: int = 0
    elapsed_seconds: float = 0.0


class BudgetTracker:
    """Thread-safe budget tracker with circuit breaker.

    Tracks cost, tokens, tool calls, and elapsed time against configured limits.
    Raises BudgetExceededError when a threshold is hit.
    """

    def __init__(
        self,
        budgets: Optional[ResourceBudgets] = None,
        cost_callback: Optional[Callable[[], float]] = None,
    ) -> None:
        """
        Args:
            budgets: Resource limits to enforce. None = no enforcement.
            cost_callback: Optional callable that returns current accumulated cost.
                          If not provided, cost must be reported via add_cost().
        """
        self._budgets = budgets
        self._cost_callback = cost_callback
        self._lock = threading.Lock()
        self._cost_usd: float = 0.0
        self._tokens: int = 0
        self._tool_calls: int = 0
        self._start_time: float = time.monotonic()

    @property
    def is_configured(self) -> bool:
        """Whether any budget limits are configured."""
        return self._budgets is not None

    def snapshot(self) -> BudgetSnapshot:
        """Get a thread-safe snapshot of current consumption."""
        with self._lock:
            cost = self._cost_callback() if self._cost_callback else self._cost_usd
            return BudgetSnapshot(
                cost_usd=cost,
                tokens=self._tokens,
                tool_calls=self._tool_calls,
                elapsed_seconds=time.monotonic() - self._start_time,
            )

    def add_cost(self, amount: float) -> None:
        """Record cost and check against limit."""
        if amount < 0:
            raise ValueError("Cost amount must be non-negative.")
        with self._lock:
            self._cost_usd += amount
            self._check_cost()

    def add_tokens(self, count: int) -> None:
        """Record token usage and check against limit."""
        if count < 0:
            raise ValueError("Token count must be non-negative.")
        with self._lock:
            self._tokens += count
            self._check_tokens()

    def record_tool_call(self) -> None:
        """Record a tool call and check against limit."""
        with self._lock:
            self._tool_calls += 1
            self._check_tool_calls()

    def check_all(self) -> None:
        """Check all budget limits. Raises BudgetExceededError on first violation."""
        with self._lock:
            self._check_cost()
            self._check_tokens()
            self._check_tool_calls()
            self._check_duration()

    def check_duration(self) -> None:
        """Check elapsed time against limit."""
        with self._lock:
            self._check_duration()

    def _check_cost(self) -> None:
        if self._budgets and self._budgets.max_cost_usd is not None:
            cost = self._cost_callback() if self._cost_callback else self._cost_usd
            if cost > self._budgets.max_cost_usd:
                raise BudgetExceededError("cost_usd", cost, self._budgets.max_cost_usd)

    def _check_tokens(self) -> None:
        if self._budgets and self._budgets.max_tokens is not None:
            if self._tokens > self._budgets.max_tokens:
                raise BudgetExceededError(
                    "tokens", float(self._tokens), float(self._budgets.max_tokens)
                )

    def _check_tool_calls(self) -> None:
        if self._budgets and self._budgets.max_tool_calls is not None:
            if self._tool_calls > self._budgets.max_tool_calls:
                raise BudgetExceededError(
                    "tool_calls",
                    float(self._tool_calls),
                    float(self._budgets.max_tool_calls),
                )

    def _check_duration(self) -> None:
        if self._budgets and self._budgets.max_duration_seconds is not None:
            elapsed = time.monotonic() - self._start_time
            if elapsed > self._budgets.max_duration_seconds:
                raise BudgetExceededError(
                    "duration_seconds", elapsed, self._budgets.max_duration_seconds
                )

    def reset(self) -> None:
        """Reset all counters and restart the timer."""
        with self._lock:
            self._cost_usd = 0.0
            self._tokens = 0
            self._tool_calls = 0
            self._start_time = time.monotonic()
