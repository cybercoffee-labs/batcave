"""
Base operator scaffolding for Bat-family execution personas.

Operators define control surfaces for observation, simulation, and eventual
execution modes. This file intentionally contains no trading logic.
"""

from __future__ import annotations


class BaseOperator:
    """Abstract base class for operator roles."""

    name: str = "base_operator"
    mode: str = "observe"

    def observe(self):
        """Observe system state without performing actions."""
        raise NotImplementedError

    def simulate(self):
        """Simulate decision paths without live execution."""
        raise NotImplementedError

    def execute(self):
        """Execute actions once a concrete operator implementation exists."""
        raise NotImplementedError
