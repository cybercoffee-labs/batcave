"""
Unit tests for core/lucius.py - LUCIUS FOX (ATLAS) Compliance Module.

Tests cover:
- Jurisdiction rules for all 4 LATAM pairs (MXN, ARS, COP, VES)
- Operating hours validation (SPEI hours for MXN)
- Amount limits (single and daily)
- AML flags and warnings
- Disabled jurisdiction blocking
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.lucius import (
    check_jurisdiction,
    is_operating_hours,
    get_daily_exposure,
    get_jurisdiction_summary,
    check_all_jurisdictions,
    JURISDICTION_RULES,
)


# ───────────────────────── JURISDICTION RULES TESTS ─────────────────────────


def test_jurisdiction_rules_exist():
    """Test that all 4 LATAM pairs have jurisdiction rules defined."""
    expected_pairs = ["MXN", "ARS", "COP", "VES"]
    for fiat in expected_pairs:
        assert fiat in JURISDICTION_RULES, f"Missing jurisdiction rules for {fiat}"


def test_mxn_rules_defined():
    """Test MXN jurisdiction rules are correctly defined."""
    rules = JURISDICTION_RULES["MXN"]
    assert rules["enabled"] is True
    assert rules["timezone"] == "America/Mexico_City"
    assert rules["operating_hours"]["is_24_7"] is False
    assert rules["operating_hours"]["start"] == dt_time(5, 0)
    assert rules["operating_hours"]["end"] == dt_time(23, 30)
    assert rules["limits"]["max_single_transfer_usd"] == 2500
    assert rules["limits"]["daily_limit_usd"] == 10000
    assert "SPEI" in rules["allowed_methods"]


def test_ars_rules_defined():
    """Test ARS jurisdiction rules are correctly defined."""
    rules = JURISDICTION_RULES["ARS"]
    assert rules["enabled"] is True
    assert rules["operating_hours"]["is_24_7"] is True
    assert rules["limits"]["max_single_transfer_usd"] == 500
    assert rules["limits"]["daily_limit_usd"] == 2000
    assert "CVU" in rules["allowed_methods"]


def test_cop_rules_disabled():
    """Test COP jurisdiction is disabled."""
    rules = JURISDICTION_RULES["COP"]
    assert rules["enabled"] is False
    assert rules["limits"]["max_single_transfer_usd"] == 1200


def test_ves_rules_disabled():
    """Test VES jurisdiction is disabled."""
    rules = JURISDICTION_RULES["VES"]
    assert rules["enabled"] is False
    assert rules["limits"]["max_single_transfer_usd"] == 100


# ───────────────────────── OPERATING HOURS TESTS ─────────────────────────


def test_is_operating_hours_24_7_market():
    """Test 24/7 markets (ARS) are always open."""
    # ARS is 24/7
    assert is_operating_hours("ARS") is True


def test_is_operating_hours_mxn_during_spei():
    """Test MXN is open during SPEI hours."""
    # Mock time to be within SPEI hours (10:00 Mexico City)
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is True


def test_is_operating_hours_mxn_outside_spei():
    """Test MXN is closed outside SPEI hours."""
    # Mock time to be outside SPEI hours (3:00 Mexico City)
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(3, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is False


def test_is_operating_hours_mxn_at_boundary_start():
    """Test MXN at SPEI start boundary (05:00)."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(5, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is True


def test_is_operating_hours_mxn_at_boundary_end():
    """Test MXN at SPEI end boundary (23:30)."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(23, 30)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is True


def test_is_operating_hours_mxn_after_boundary():
    """Test MXN after SPEI end (23:31)."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(23, 31)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        assert is_operating_hours("MXN") is False


def test_is_operating_hours_unknown_fiat():
    """Test unknown fiat returns False."""
    assert is_operating_hours("XYZ") is False


# ───────────────────────── CHECK JURISDICTION TESTS ─────────────────────────


def test_check_jurisdiction_mxn_approved():
    """Test MXN approval for valid amount during operating hours."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)  # During SPEI hours

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        with patch("core.lucius.get_daily_exposure", return_value=0.0):
            result = check_jurisdiction("MXN", amount_usd=500)

    assert result["approved"] is True
    assert result["blocked_by"] is None
    assert result["checks"]["jurisdiction_enabled"] is True
    assert result["checks"]["operating_hours"] is True
    assert result["checks"]["single_amount_limit"] is True
    assert result["checks"]["daily_exposure_limit"] is True


def test_check_jurisdiction_disabled_pair():
    """Test disabled pair (COP) is blocked."""
    result = check_jurisdiction("COP", amount_usd=100)

    assert result["approved"] is False
    assert "JURISDICTION_DISABLED" in result["blocked_by"]
    assert result["checks"]["jurisdiction_enabled"] is False


def test_check_jurisdiction_outside_hours():
    """Test MXN blocked outside SPEI hours."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(3, 0)  # Outside SPEI hours

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        result = check_jurisdiction("MXN", amount_usd=500)

    assert result["approved"] is False
    assert "OUTSIDE_OPERATING_HOURS" in result["blocked_by"]
    assert result["checks"]["operating_hours"] is False


def test_check_jurisdiction_exceeds_single_limit():
    """Test blocking when amount exceeds single transfer limit."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        # MXN max single is $2,500 USD
        result = check_jurisdiction("MXN", amount_usd=3000)

    assert result["approved"] is False
    assert "EXCEEDS_SINGLE_LIMIT" in result["blocked_by"]
    assert result["checks"]["single_amount_limit"] is False


def test_check_jurisdiction_exceeds_daily_limit():
    """Test blocking when daily exposure limit exceeded."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        # Mock that $9,500 already used today (MXN daily limit is $10,000)
        with patch("core.lucius.get_daily_exposure", return_value=9500.0):
            result = check_jurisdiction("MXN", amount_usd=1000)

    assert result["approved"] is False
    assert "EXCEEDS_DAILY_LIMIT" in result["blocked_by"]
    assert result["checks"]["daily_exposure_limit"] is False


def test_check_jurisdiction_aml_flag():
    """Test AML warning when amount exceeds flag threshold."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        with patch("core.lucius.get_daily_exposure", return_value=0.0):
            # MXN AML flag threshold is $500 USD
            result = check_jurisdiction("MXN", amount_usd=600)

    assert result["approved"] is True  # Still approved, just flagged
    assert any("AML_FLAG" in w for w in result["warnings"])
    assert result["checks"]["aml_flag"] == "FLAGGED"


def test_check_jurisdiction_unknown_fiat():
    """Test unknown fiat is blocked."""
    result = check_jurisdiction("XYZ", amount_usd=100)

    assert result["approved"] is False
    assert "UNKNOWN_JURISDICTION" in result["blocked_by"]


def test_check_jurisdiction_ars_lower_limits():
    """Test ARS has lower limits than MXN."""
    # ARS max single is $500 USD
    result = check_jurisdiction("ARS", amount_usd=600)

    assert result["approved"] is False
    assert "EXCEEDS_SINGLE_LIMIT" in result["blocked_by"]


def test_check_jurisdiction_ars_approved():
    """Test ARS approval for valid amount (24/7 market)."""
    with patch("core.lucius.get_daily_exposure", return_value=0.0):
        result = check_jurisdiction("ARS", amount_usd=400)

    assert result["approved"] is True


# ───────────────────────── DAILY EXPOSURE TESTS ─────────────────────────


def test_get_daily_exposure_no_file(tmp_path):
    """Test daily exposure returns 0 when harvey DB has no data."""
    with patch("core.harvey.daily_exposure", return_value=0.0):
        with patch("core.lucius.EXECUTIONS_FILE", tmp_path / "nonexistent.jsonl"):
            exposure = get_daily_exposure("MXN")
    assert exposure == 0.0


def test_get_daily_exposure_with_data(tmp_path):
    """Test daily exposure returns HARVEY DB value as single source of truth."""
    log_file = tmp_path / "opportunities.jsonl"
    today = datetime.now(timezone.utc).date().isoformat()

    # Write JSONL data (mirrors what would be in harvey DB)
    test_data = [
        {"ts": f"{today}T10:00:00+00:00", "market": "MXN", "depth_estimate": 500},
        {"ts": f"{today}T11:00:00+00:00", "market": "MXN", "depth_estimate": 300},
        {"ts": f"{today}T12:00:00+00:00", "market": "ARS", "depth_estimate": 200},  # Different pair
        {"ts": "2024-01-01T10:00:00+00:00", "market": "MXN", "depth_estimate": 1000},  # Old date
    ]

    with open(log_file, "w") as f:
        for record in test_data:
            f.write(json.dumps(record) + "\n")

    # Harvey DB is the source of truth: returns 800.0 (500 + 300 for MXN today)
    with patch("core.harvey.daily_exposure", return_value=800.0):
        with patch("core.lucius.EXECUTIONS_FILE", log_file):
            exposure = get_daily_exposure("MXN")

    assert exposure == 800.0


# ───────────────────────── SUMMARY TESTS ─────────────────────────


def test_get_jurisdiction_summary():
    """Test jurisdiction summary format."""
    summary = get_jurisdiction_summary("MXN")

    assert summary["fiat"] == "MXN"
    assert summary["name"] == "Mexico"
    assert summary["enabled"] is True
    assert summary["is_24_7"] is False
    assert summary["max_single_usd"] == 2500
    assert summary["daily_limit_usd"] == 10000
    assert "SPEI" in summary["allowed_methods"]


def test_get_jurisdiction_summary_unknown():
    """Test summary for unknown fiat."""
    summary = get_jurisdiction_summary("XYZ")
    assert summary["status"] == "UNKNOWN"


def test_check_all_jurisdictions():
    """Test all jurisdictions are included in summary."""
    all_jurisdictions = check_all_jurisdictions()

    assert "MXN" in all_jurisdictions
    assert "ARS" in all_jurisdictions
    assert "COP" in all_jurisdictions
    assert "VES" in all_jurisdictions

    # Verify enabled status
    assert all_jurisdictions["MXN"]["enabled"] is True
    assert all_jurisdictions["ARS"]["enabled"] is True
    assert all_jurisdictions["COP"]["enabled"] is False
    assert all_jurisdictions["VES"]["enabled"] is False


# ───────────────────────── INTEGRATION TESTS ─────────────────────────


def test_full_workflow_mxn_approved():
    """Integration test: Full MXN approval workflow."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(10, 0)

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        with patch("core.lucius.get_daily_exposure", return_value=1000.0):
            result = check_jurisdiction("MXN", amount_usd=1000)

    assert result["approved"] is True
    assert result["daily_exposure_usd"] == 1000.0
    assert result["jurisdiction"]["name"] == "Mexico"


def test_full_workflow_mxn_blocked_composite():
    """Integration test: Verify all checks run in order."""
    mock_dt = MagicMock()
    mock_dt.time.return_value = dt_time(3, 0)  # Outside hours

    with patch("core.lucius._get_local_time", return_value=mock_dt):
        result = check_jurisdiction("MXN", amount_usd=5000)  # Also exceeds limit

    # Should block on hours first, not reach amount check
    assert result["approved"] is False
    assert "OUTSIDE_OPERATING_HOURS" in result["blocked_by"]
    # Amount check should not have been evaluated
    assert result["checks"]["single_amount_limit"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
