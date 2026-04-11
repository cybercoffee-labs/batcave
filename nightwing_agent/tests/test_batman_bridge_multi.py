"""
Tests for Batman Bridge Multi-Strategy Functions

Tests fetch_best_opportunity() for multi-type, multi-fiat filtering.
"""

import json
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from core.batman_bridge import fetch_best_opportunity


def _make_opp(opp_id, opp_type, market, edge_net, age_seconds=60):
    """Helper to create opportunity records."""
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return json.dumps(
        {
            "opp_id": opp_id,
            "ts": ts.isoformat(),
            "type": opp_type,
            "market": market,
            "edge_net": edge_net,
            "viable": edge_net > 0,
            "scanner_id": f"{opp_type}-TEST",
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test fetch_best_opportunity
# ─────────────────────────────────────────────────────────────────────────────


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_returns_highest_edge(mock_path):
    """Test that highest edge_net opportunity is returned."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "MXN", 0.50),
            _make_opp("OPP-C-002", "C", "MXN", 0.80),  # Best
            _make_opp("OPP-C-003", "C", "MXN", 0.30),
        ]
    )

    result = fetch_best_opportunity(fiats=["MXN"])

    assert result["status"] == "ok"
    assert result["edge_net"] == 0.80
    assert result["opp_id"] == "OPP-C-002"


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_filters_by_fiat(mock_path):
    """Test filtering by fiat currency."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "MXN", 0.50),
            _make_opp("OPP-C-002", "C", "ARS", 0.90),  # Different fiat
            _make_opp("OPP-C-003", "C", "MXN", 0.70),
        ]
    )

    result = fetch_best_opportunity(fiats=["MXN"])

    assert result["status"] == "ok"
    assert result["edge_net"] == 0.70
    assert result["fiat"] == "MXN"


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_filters_by_type(mock_path):
    """Test filtering by opportunity type."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "MXN", 0.50),
            _make_opp("OPP-D-001", "D", "MXN", 0.90),  # Different type
            _make_opp("OPP-C-002", "C", "MXN", 0.70),
        ]
    )

    result = fetch_best_opportunity(fiats=["MXN"], types=["C"])

    assert result["status"] == "ok"
    assert result["type"] == "C"
    assert result["edge_net"] == 0.70


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_accepts_multiple_types(mock_path):
    """Test accepting multiple opportunity types."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "MXN", 0.50),
            _make_opp("OPP-D-001", "D", "MXN", 0.90),  # Best D
            _make_opp("OPP-F-001", "F", "MXN", 0.70),
        ]
    )

    result = fetch_best_opportunity(fiats=["MXN"], types=["C", "D"])

    assert result["status"] == "ok"
    assert result["type"] == "D"
    assert result["edge_net"] == 0.90


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_excludes_stale(mock_path):
    """Test that stale records (>1200s) are excluded."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "MXN", 0.50, age_seconds=60),
            _make_opp("OPP-C-002", "C", "MXN", 0.90, age_seconds=1500),  # Stale
        ]
    )

    result = fetch_best_opportunity(fiats=["MXN"])

    assert result["status"] == "ok"
    assert result["edge_net"] == 0.50  # Not the stale one


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_no_match(mock_path):
    """Test when no opportunities match criteria."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "ARS", 0.50),  # Wrong fiat
        ]
    )

    result = fetch_best_opportunity(fiats=["MXN"])

    assert result["status"] == "no_match"


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_file_not_found(mock_path):
    """Test error when opportunities file doesn't exist."""
    mock_path.exists.return_value = False

    result = fetch_best_opportunity(fiats=["MXN"])

    assert result["status"] == "error"
    assert "not_found" in result["error"]


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_includes_raw_record(mock_path):
    """Test that raw_record is included in result."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = _make_opp("OPP-C-001", "C", "MXN", 0.50)

    result = fetch_best_opportunity(fiats=["MXN"])

    assert result["status"] == "ok"
    assert "raw_record" in result
    assert result["raw_record"]["opp_id"] == "OPP-C-001"


@patch("core.batman_bridge.BATMAN_OPPS")
def test_fetch_best_opportunity_default_fiats(mock_path):
    """Test default fiats is MXN."""
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "\n".join(
        [
            _make_opp("OPP-C-001", "C", "MXN", 0.50),
            _make_opp("OPP-C-002", "C", "ARS", 0.90),  # Higher but different fiat
        ]
    )

    # Default should be MXN
    result = fetch_best_opportunity()

    assert result["status"] == "ok"
    assert result["fiat"] == "MXN"
