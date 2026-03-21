"""
Unit tests for core/lucius.py - LUCIUS FOX (ATLAS) Compliance Module.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import time as dt_time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.lucius import (
    check_jurisdiction,
    is_operating_hours,
    get_daily_exposure,
    get_jurisdiction_summary,
    JURISDICTION_RULES,
)


# ───────────────────────── JURISDICTION RULES TESTS ─────────────────────────


def test_jurisdiction_rules_exist():
    expected = ["MXN", "ARS", "COP", "VES"]
    for fiat in expected:
        assert fiat in JURISDICTION_RULES


def test_mxn_rules_correct():
    rules = JURISDICTION_RULES["MXN"]
    assert rules["enabled"] is True
    assert rules["timezone"] == "America/Mexico_City"
    assert rules["operating_hours"]["is_24_7"] is False
    assert rules["operating_hours"]["start"] == dt_time(5, 0)
    assert rules["operating_hours"]["end"] == dt_time(23, 30)
    assert rules["limits"]["max_single_transfer_usd"] == 2500
    assert rules["limits"]["daily_limit_usd"] == 10000


def test_ars_rules_correct():
    rules = JURISDICTION_RULES["ARS"]
    assert rules["enabled"] is True
    assert rules["operating_hours"]["is_24_7"] is True
    assert rules["limits"]["max_single_transfer_usd"] == 500
    assert rules["limits"]["daily_limit_usd"] == 2000


def test_cop_disabled():
    assert JURISDICTION_RULES["COP"]["enabled"] is False


def test_ves_disabled():
    assert JURISDICTION_RULES["VES"]["enabled"] is False


# ───────────────────────── OPERATING HOURS TESTS ─────────────────────────


def test_is_operating_hours_24_7():
    assert is_operating_hours("ARS") is True


def test_is_operating_hours_mxn_during_spei():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is True


def test_is_operating_hours_mxn_outside_spei():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(3, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is False


def test_is_operating_hours_mxn_boundary_start():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(5, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is True


def test_is_operating_hours_mxn_boundary_end():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(23, 30)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is True


def test_is_operating_hours_unknown():
    assert is_operating_hours("XYZ") is False


# ───────────────────────── CHECK JURISDICTION TESTS ─────────────────────────


def test_check_jurisdiction_mxn_approved():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        with patch("core.lucius.get_daily_exposure", return_value=0.0):
            result = check_jurisdiction("MXN", 500)
    assert result["approved"] is True
    assert result["blocked_by"] is None


def test_check_jurisdiction_disabled_pair():
    result = check_jurisdiction("COP", 100)
    assert result["approved"] is False
    assert "JURISDICTION_DISABLED" in result["blocked_by"]


def test_check_jurisdiction_outside_hours():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(3, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        result = check_jurisdiction("MXN", 500)
    assert result["approved"] is False
    assert "OUTSIDE_OPERATING_HOURS" in result["blocked_by"]


def test_check_jurisdiction_exceeds_single_limit():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        result = check_jurisdiction("MXN", 3000)
    assert result["approved"] is False
    assert "EXCEEDS_SINGLE_LIMIT" in result["blocked_by"]


def test_check_jurisdiction_exceeds_daily_limit():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        with patch("core.lucius.get_daily_exposure", return_value=9500.0):
            result = check_jurisdiction("MXN", 1000)
    assert result["approved"] is False
    assert "EXCEEDS_DAILY_LIMIT" in result["blocked_by"]


def test_check_jurisdiction_aml_flag():
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)
    with patch("core.lucius._get_local_time", return_value=mock_dt):
        with patch("core.lucius.get_daily_exposure", return_value=0.0):
            result = check_jurisdiction("MXN", 600)
    assert result["approved"] is True
    assert any("AML_FLAG" in w for w in result["warnings"])


def test_check_jurisdiction_unknown():
    result = check_jurisdiction("XYZ", 100)
    assert result["approved"] is False
    assert "UNKNOWN_JURISDICTION" in result["blocked_by"]


def test_check_jurisdiction_ars_limits():
    result = check_jurisdiction("ARS", 600)
    assert result["approved"] is False
    assert "EXCEEDS_SINGLE_LIMIT" in result["blocked_by"]


def test_check_jurisdiction_ars_approved():
    with patch("core.lucius.get_daily_exposure", return_value=0.0):
        result = check_jurisdiction("ARS", 400)
    assert result["approved"] is True


# ───────────────────────── DAILY EXPOSURE TESTS ─────────────────────────


def test_get_daily_exposure_no_file(tmp_path):
    """Test returns 0 when no files exist."""
    with (
        patch("core.lucius.EXECUTIONS_FILE", tmp_path / "nonexistent.jsonl"),
        patch("core.lucius.LEDGER_FILE", tmp_path / "nonexistent_ledger.jsonl"),
    ):
        assert get_daily_exposure("MXN") == 0.0


# ───────────────────────── SUMMARY TESTS ─────────────────────────


def test_get_jurisdiction_summary():
    summary = get_jurisdiction_summary("MXN")
    assert summary["fiat"] == "MXN"
    assert summary["name"] == "Mexico"
    assert summary["enabled"] is True
    assert summary["max_single_usd"] == 2500


def test_get_jurisdiction_summary_unknown():
    summary = get_jurisdiction_summary("XYZ")
    assert summary["status"] == "UNKNOWN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
