"""
Red Robin operator scaffold.

This module defines only the structural placeholder for a future operator role.
"""

from __future__ import annotations

from operators.base_operator import BaseOperator


class RedRobinOperator(BaseOperator):
    """Placeholder operator with no live trading logic."""

    name = "red_robin"
    mode = "observe"

    def observe(self):
        """Return a placeholder observation payload."""
        return {"operator": self.name, "mode": self.mode, "status": "not_implemented"}

    def simulate(self):
        """Return a placeholder simulation payload."""
        return {"operator": self.name, "mode": self.mode, "status": "not_implemented"}

    def execute(self):
        """Execution is intentionally unavailable in this scaffold."""
        raise NotImplementedError("Red Robin execution is not implemented.")
