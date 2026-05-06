"""Test fixtures shared across the entire batman_flow_engine test suite.

Most importantly: disable BATDETECTIVE network fetchers by default. Any
test that calls run_engine() (commander, gordon, risk_scores, etc.) gets
a deterministic, network-free cycle. Tests that explicitly want to exercise
BATDETECTIVE pass `sources=` directly to run_batdetective_cycle, which
bypasses the env-var gate.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_batdetective_fetchers():
    """Disable network calls in BATDETECTIVE for the whole test session."""
    prev = os.environ.get("BATMAN_DISABLE_BATDETECTIVE")
    os.environ["BATMAN_DISABLE_BATDETECTIVE"] = "1"
    yield
    if prev is None:
        os.environ.pop("BATMAN_DISABLE_BATDETECTIVE", None)
    else:
        os.environ["BATMAN_DISABLE_BATDETECTIVE"] = prev
