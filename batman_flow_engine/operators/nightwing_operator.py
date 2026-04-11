"""
Nightwing operator scaffold.

Nightwing remains a separate repository. This local class exists only to define
the interface boundary that Batcave can rely on later.
"""

from __future__ import annotations

from operators.base_operator import BaseOperator


class NightwingOperator(BaseOperator):
    """Placeholder adapter for the Nightwing control surface."""

    name = "nightwing"
    mode = "external"

    def observe(self):
        """Return a placeholder observation payload."""
        return {"operator": self.name, "mode": self.mode, "status": "not_implemented"}

    def simulate(self):
        """Return a placeholder simulation payload."""
        return {"operator": self.name, "mode": self.mode, "status": "not_implemented"}

    def execute(self):
        """Execution is intentionally unavailable in this scaffold."""
        raise NotImplementedError("Nightwing execution is managed in a separate repository.")
