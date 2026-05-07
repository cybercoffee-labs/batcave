"""Tests for core/cycle_context.py (audit Section C #9 — correlation IDs)."""

from __future__ import annotations

import re

import pytest


@pytest.fixture(autouse=True)
def _reset_cycle_context():
    """Ensure no test starts or ends with a leaked cycle id."""
    from core.cycle_context import clear_current_cycle_id

    clear_current_cycle_id()
    yield
    clear_current_cycle_id()


def test_new_cycle_id_returns_12_hex_chars():
    from core.cycle_context import new_cycle_id

    cycle_id = new_cycle_id()
    assert isinstance(cycle_id, str)
    assert re.fullmatch(r"[0-9a-f]{12}", cycle_id), f"Got: {cycle_id!r}"


def test_new_cycle_id_returns_unique_values():
    from core.cycle_context import new_cycle_id

    ids = {new_cycle_id() for _ in range(50)}
    # 50 values from 48 bits of entropy — collision probability is astronomical.
    assert len(ids) == 50


def test_get_returns_none_when_no_cycle_in_flight():
    from core.cycle_context import get_current_cycle_id

    assert get_current_cycle_id() is None


def test_set_then_get_round_trip():
    from core.cycle_context import (
        get_current_cycle_id,
        set_current_cycle_id,
    )

    set_current_cycle_id("abc123def456")
    assert get_current_cycle_id() == "abc123def456"


def test_clear_resets_state():
    from core.cycle_context import (
        clear_current_cycle_id,
        get_current_cycle_id,
        set_current_cycle_id,
    )

    set_current_cycle_id("abc123def456")
    clear_current_cycle_id()
    assert get_current_cycle_id() is None


def test_set_rejects_empty_string():
    from core.cycle_context import set_current_cycle_id

    with pytest.raises(ValueError):
        set_current_cycle_id("")


def test_stamp_writes_cycle_id_when_context_active():
    from core.cycle_context import set_current_cycle_id, stamp_cycle_id

    set_current_cycle_id("abc123def456")
    opp = {"opp_id": "OPP-A-X"}
    out = stamp_cycle_id(opp)
    assert out is opp  # mutates in place
    assert opp["cycle_id"] == "abc123def456"


def test_stamp_preserves_existing_cycle_id():
    from core.cycle_context import set_current_cycle_id, stamp_cycle_id

    set_current_cycle_id("abc123def456")
    opp = {"opp_id": "OPP-A-X", "cycle_id": "existing_id_99"}
    stamp_cycle_id(opp)
    # An opp that already declared its own cycle_id is left alone.
    assert opp["cycle_id"] == "existing_id_99"


def test_stamp_is_no_op_without_active_context():
    from core.cycle_context import stamp_cycle_id

    opp = {"opp_id": "OPP-A-X"}
    stamp_cycle_id(opp)
    assert "cycle_id" not in opp


def test_stamp_handles_non_dict_input_gracefully():
    """An ad-hoc CLI scanner could pass a list or string. Don't crash."""
    from core.cycle_context import set_current_cycle_id, stamp_cycle_id

    set_current_cycle_id("abc123def456")
    assert stamp_cycle_id([1, 2, 3]) == [1, 2, 3]
    assert stamp_cycle_id("not a dict") == "not a dict"
