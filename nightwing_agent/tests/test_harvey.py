"""
Tests for core/harvey.py — Trade Execution Ledger
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from core import harvey
from core.harvey import (
    record_trade,
    _read_ledger,
    get_daily_summary,
    get_session_summary,
    print_summary,
    _summarize,
)


# ============================================================================
# record_trade tests
# ============================================================================


def test_record_trade_creates_file(tmp_path):
    """record_trade creates trades.jsonl file if it doesn't exist."""
    ledger_file = tmp_path / "ledger" / "trades.jsonl"

    result = {
        "ts": "2026-03-13T10:00:00+00:00",
        "cycle": 1,
        "mode": "SIMULATED",
        "fiat": "MXN",
        "amount_usd": 500.0,
        "decision": "OPPORTUNITY",
        "action": "LOGGED",
        "status": "complete",
        "edge_net": 0.44,
        "duration_ms": 15,
        "batman": {
            "status": "ok",
            "viable": True,
            "opp_id": "OPP-C-12345678",
            "total_friction_pct": 0.25,
            "spot_price": 17.787209,
            "p2p_buy_price": 17.91,
            "p2p_sell_price": 17.878,
            "depth_estimate": 13176.84,
        },
    }

    with patch.object(harvey, "LEDGER_FILE", ledger_file):
        record_trade(result)

    assert ledger_file.exists()
    lines = ledger_file.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["cycle"] == 1
    assert record["decision"] == "OPPORTUNITY"


def test_record_trade_appends_multiple_records(tmp_path):
    """record_trade appends multiple records correctly."""
    ledger_file = tmp_path / "trades.jsonl"

    results = [
        {"ts": "2026-03-13T10:00:00+00:00", "cycle": 1, "decision": "PASS", "edge_net": 0.05, "batman": {}},
        {"ts": "2026-03-13T10:05:00+00:00", "cycle": 2, "decision": "OPPORTUNITY", "edge_net": 0.44, "batman": {}},
        {"ts": "2026-03-13T10:10:00+00:00", "cycle": 3, "decision": "PASS", "edge_net": 0.08, "batman": {}},
    ]

    with patch.object(harvey, "LEDGER_FILE", ledger_file):
        for r in results:
            record_trade(r)

    lines = ledger_file.read_text().strip().split("\n")
    assert len(lines) == 3

    for i, line in enumerate(lines):
        record = json.loads(line)
        assert record["cycle"] == i + 1


def test_record_trade_handles_missing_batman_dict(tmp_path):
    """record_trade handles missing batman dict gracefully."""
    ledger_file = tmp_path / "trades.jsonl"

    result = {
        "ts": "2026-03-13T10:00:00+00:00",
        "cycle": 1,
        "decision": "PASS",
        "edge_net": 0.0,
        # No batman key at all
    }

    with patch.object(harvey, "LEDGER_FILE", ledger_file):
        record_trade(result)  # Should not raise

    assert ledger_file.exists()
    record = json.loads(ledger_file.read_text().strip())
    assert record["viable"] is None
    assert record["opp_id"] is None


def test_record_trade_handles_empty_result_dict(tmp_path):
    """record_trade handles empty result dict gracefully."""
    ledger_file = tmp_path / "trades.jsonl"

    with patch.object(harvey, "LEDGER_FILE", ledger_file):
        record_trade({})  # Should not raise

    assert ledger_file.exists()
    record = json.loads(ledger_file.read_text().strip())
    assert record["timestamp"] is None
    assert record["cycle"] is None
    assert record["decision"] is None


def test_record_trade_extracts_batman_bridge_data(tmp_path):
    """record_trade extracts batman bridge data correctly (viable, opp_id, prices, friction)."""
    ledger_file = tmp_path / "trades.jsonl"

    result = {
        "ts": "2026-03-13T10:00:00+00:00",
        "cycle": 1,
        "decision": "OPPORTUNITY",
        "edge_net": 0.44,
        "batman": {
            "status": "ok",
            "viable": True,
            "opp_id": "OPP-C-ABCD1234",
            "total_friction_pct": 0.25,
            "spot_price": 17.787209,
            "p2p_buy_price": 17.91,
            "p2p_sell_price": 17.878,
            "depth_estimate": 13176.84,
        },
    }

    with patch.object(harvey, "LEDGER_FILE", ledger_file):
        record_trade(result)

    record = json.loads(ledger_file.read_text().strip())
    assert record["viable"] is True
    assert record["opp_id"] == "OPP-C-ABCD1234"
    assert record["total_friction_pct"] == 0.25
    assert record["spot_price"] == 17.787209
    assert record["p2p_buy_price"] == 17.91
    assert record["p2p_sell_price"] == 17.878
    assert record["depth_estimate"] == 13176.84


def test_record_trade_handles_stale_batman_data(tmp_path):
    """record_trade extracts data from stale batman status correctly."""
    ledger_file = tmp_path / "trades.jsonl"

    result = {
        "ts": "2026-03-13T10:00:00+00:00",
        "cycle": 1,
        "decision": "PASS",
        "edge_net": 0.30,
        "batman": {
            "status": "stale",
            "data": {
                "viable": True,
                "opp_id": "OPP-C-STALE123",
                "total_friction_pct": 0.40,
                "spot_price": 18.0,
                "p2p_buy_price": 18.1,
                "p2p_sell_price": 18.05,
                "depth_estimate": 8000.0,
            },
        },
    }

    with patch.object(harvey, "LEDGER_FILE", ledger_file):
        record_trade(result)

    record = json.loads(ledger_file.read_text().strip())
    assert record["viable"] is True
    assert record["opp_id"] == "OPP-C-STALE123"
    assert record["total_friction_pct"] == 0.40


# ============================================================================
# get_daily_summary tests
# ============================================================================


def test_get_daily_summary_with_mixed_decisions(tmp_path):
    """get_daily_summary with mixed decisions (PASS + OPPORTUNITY + BLOCKED)."""
    ledger_file = tmp_path / "trades.jsonl"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = [
        {"timestamp": f"{today}T10:00:00+00:00", "decision": "PASS", "edge_net": 0.05, "viable": False},
        {"timestamp": f"{today}T10:05:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
        {"timestamp": f"{today}T10:10:00+00:00", "decision": "BLOCKED_COMPLIANCE", "edge_net": 0.0, "viable": False},
        {"timestamp": f"{today}T10:15:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.55, "viable": True},
    ]

    ledger_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    summary = get_daily_summary(path=ledger_file)

    assert summary["total_cycles"] == 4
    assert summary["opportunities"] == 2
    assert summary["passes"] == 1
    assert summary["blocked"] == 1


def test_get_daily_summary_empty_ledger(tmp_path):
    """get_daily_summary with empty ledger returns all zeros."""
    ledger_file = tmp_path / "trades.jsonl"
    # File doesn't exist

    summary = get_daily_summary(path=ledger_file)

    assert summary["total_cycles"] == 0
    assert summary["opportunities"] == 0
    assert summary["passes"] == 0
    assert summary["blocked"] == 0
    assert summary["avg_edge_net"] == 0.0
    assert summary["viable_pct"] == 0.0


def test_get_daily_summary_only_counts_today(tmp_path):
    """get_daily_summary only counts today's records (not yesterday's)."""
    ledger_file = tmp_path / "trades.jsonl"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    records = [
        {"timestamp": f"{yesterday}T10:00:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.50, "viable": True},
        {"timestamp": f"{yesterday}T10:05:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.60, "viable": True},
        {"timestamp": f"{today}T10:00:00+00:00", "decision": "PASS", "edge_net": 0.05, "viable": False},
    ]

    ledger_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    summary = get_daily_summary(path=ledger_file)

    assert summary["total_cycles"] == 1  # Only today's record
    assert summary["opportunities"] == 0
    assert summary["passes"] == 1


# ============================================================================
# get_session_summary tests
# ============================================================================


def test_get_session_summary_filters_by_timestamp(tmp_path):
    """get_session_summary filters by timestamp correctly."""
    ledger_file = tmp_path / "trades.jsonl"

    records = [
        {"timestamp": "2026-03-13T08:00:00+00:00", "decision": "PASS", "edge_net": 0.05, "viable": False},
        {"timestamp": "2026-03-13T10:00:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
        {"timestamp": "2026-03-13T12:00:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.55, "viable": True},
    ]

    ledger_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    # Filter from 09:00 onwards — should get only the last 2 records
    summary = get_session_summary("2026-03-13T09:00:00+00:00", path=ledger_file)

    assert summary["total_cycles"] == 2
    assert summary["opportunities"] == 2
    assert summary["passes"] == 0


def test_get_session_summary_no_matching_records(tmp_path):
    """get_session_summary with no matching records returns zeros."""
    ledger_file = tmp_path / "trades.jsonl"

    records = [
        {"timestamp": "2026-03-13T08:00:00+00:00", "decision": "PASS", "edge_net": 0.05, "viable": False},
        {"timestamp": "2026-03-13T09:00:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
    ]

    ledger_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    # Filter from way in the future — should get no records
    summary = get_session_summary("2026-12-31T00:00:00+00:00", path=ledger_file)

    assert summary["total_cycles"] == 0
    assert summary["opportunities"] == 0
    assert summary["avg_edge_net"] == 0.0


# ============================================================================
# print_summary tests
# ============================================================================


def test_print_summary_empty_ledger(tmp_path, capsys):
    """print_summary runs without error on empty ledger."""
    ledger_file = tmp_path / "trades.jsonl"
    # File doesn't exist

    print_summary(path=ledger_file)  # Should not raise

    captured = capsys.readouterr()
    assert "HARVEY" in captured.out
    assert "Total cycles" in captured.out


def test_print_summary_with_data(tmp_path, capsys):
    """print_summary runs without error with data."""
    ledger_file = tmp_path / "trades.jsonl"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    records = [
        {"timestamp": f"{today}T10:00:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
        {"timestamp": f"{today}T10:05:00+00:00", "decision": "PASS", "edge_net": 0.08, "viable": False},
    ]

    ledger_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    print_summary(path=ledger_file)  # Should not raise

    captured = capsys.readouterr()
    assert "HARVEY" in captured.out
    assert "Total cycles:" in captured.out
    assert "Opportunities:" in captured.out


# ============================================================================
# _read_ledger tests
# ============================================================================


def test_read_ledger_handles_corrupt_lines(tmp_path):
    """_read_ledger handles corrupt JSONL lines (skip, don't crash)."""
    ledger_file = tmp_path / "trades.jsonl"

    content = """{"timestamp": "2026-03-13T10:00:00+00:00", "decision": "PASS", "edge_net": 0.05}
this is not valid JSON
{"timestamp": "2026-03-13T10:05:00+00:00", "decision": "OPPORTUNITY", "edge_net": 0.44}
also invalid {{{
{"timestamp": "2026-03-13T10:10:00+00:00", "decision": "PASS", "edge_net": 0.08}
"""
    ledger_file.write_text(content)

    records = _read_ledger(path=ledger_file)

    # Should skip corrupt lines and return only valid records
    assert len(records) == 3
    assert records[0]["edge_net"] == 0.05
    assert records[1]["edge_net"] == 0.44
    assert records[2]["edge_net"] == 0.08


def test_read_ledger_missing_file(tmp_path):
    """_read_ledger handles missing file returns empty list."""
    ledger_file = tmp_path / "nonexistent.jsonl"

    records = _read_ledger(path=ledger_file)

    assert records == []


# ============================================================================
# _summarize tests
# ============================================================================


def test_summarize_computes_edge_stats():
    """_summarize computes correct avg/best/worst edge."""
    records = [
        {"decision": "PASS", "edge_net": 0.10, "viable": False},
        {"decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
        {"decision": "OPPORTUNITY", "edge_net": 0.55, "viable": True},
        {"decision": "PASS", "edge_net": 0.05, "viable": False},
    ]

    summary = _summarize(records)

    # avg = (0.10 + 0.44 + 0.55 + 0.05) / 4 = 0.285
    assert summary["avg_edge_net"] == 0.285
    assert summary["best_edge"] == 0.55
    assert summary["worst_edge"] == 0.05


def test_summarize_computes_viable_pct():
    """_summarize computes correct viable_pct."""
    records = [
        {"decision": "PASS", "edge_net": 0.10, "viable": False},
        {"decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
        {"decision": "OPPORTUNITY", "edge_net": 0.55, "viable": True},
        {"decision": "PASS", "edge_net": 0.05, "viable": False},
    ]

    summary = _summarize(records)

    # 2 viable out of 4 = 50%
    assert summary["viable_count"] == 2
    assert summary["viable_pct"] == 50.0


def test_summarize_handles_records_without_edge():
    """_summarize handles records without edge_net field."""
    records = [
        {"decision": "PASS", "viable": False},  # No edge_net
        {"decision": "OPPORTUNITY", "edge_net": 0.44, "viable": True},
        {"decision": "BLOCKED_COMPLIANCE", "viable": False},  # No edge_net
    ]

    summary = _summarize(records)

    assert summary["total_cycles"] == 3
    # Only 1 record has edge_net
    assert summary["avg_edge_net"] == 0.44
    assert summary["best_edge"] == 0.44
    assert summary["worst_edge"] == 0.44
