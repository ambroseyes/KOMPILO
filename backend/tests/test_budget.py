"""Unit tests for the pure budget-gate decision (``budget_breach``).

No database: these pin the boundary logic (disabled = allow, opt-in, >= is a
breach, cost checked before tasks) deterministically.
"""

from __future__ import annotations

from app.services.budget import budget_breach


def test_disabled_never_breaches_even_over_limits() -> None:
    assert (
        budget_breach(enabled=False, cost_limit=1.0, task_limit=1, cost_used=100.0, tasks_used=100)
        is None
    )


def test_no_caps_is_unlimited() -> None:
    assert (
        budget_breach(
            enabled=True, cost_limit=None, task_limit=None, cost_used=999.0, tasks_used=999
        )
        is None
    )


def test_cost_under_limit_allows() -> None:
    assert (
        budget_breach(enabled=True, cost_limit=5.0, task_limit=None, cost_used=4.999, tasks_used=0)
        is None
    )


def test_cost_at_limit_breaches() -> None:
    msg = budget_breach(enabled=True, cost_limit=5.0, task_limit=None, cost_used=5.0, tasks_used=0)
    assert msg is not None and "Budget mensuel de coût" in msg


def test_cost_over_limit_breaches() -> None:
    msg = budget_breach(enabled=True, cost_limit=5.0, task_limit=None, cost_used=5.01, tasks_used=0)
    assert msg is not None and "USD" in msg


def test_task_under_limit_allows() -> None:
    assert (
        budget_breach(enabled=True, cost_limit=None, task_limit=10, cost_used=0.0, tasks_used=9)
        is None
    )


def test_task_at_limit_breaches() -> None:
    msg = budget_breach(enabled=True, cost_limit=None, task_limit=10, cost_used=0.0, tasks_used=10)
    assert msg is not None and "Quota mensuel de tâches" in msg


def test_cost_cap_takes_precedence_over_task_cap() -> None:
    # Both breached → the cost message is the one returned.
    msg = budget_breach(enabled=True, cost_limit=1.0, task_limit=1, cost_used=2.0, tasks_used=2)
    assert msg is not None and "Budget mensuel de coût" in msg
