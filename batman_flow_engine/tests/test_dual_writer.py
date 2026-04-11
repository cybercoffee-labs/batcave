"""Tests for dual writer module."""

from unittest.mock import patch


def test_dual_writer_imports():
    from core.dual_writer import log_opportunity, log_scanner_run, log_engine_run

    assert callable(log_opportunity)
    assert callable(log_scanner_run)
    assert callable(log_engine_run)


def test_log_opportunity_writes_jsonl(tmp_path):
    """Should write to JSONL even if PostgreSQL is unavailable."""
    from core.dual_writer import log_opportunity
    import json

    log_file = tmp_path / "test.jsonl"

    with patch("core.dual_writer.LOG_FILE", log_file), patch("core.dual_writer._pg_available", False):
        opp = {"opp_id": "TEST-001", "type": "C", "edge_net": 0.5, "viable": True}
        result = log_opportunity(opp)
        assert result is True

    content = log_file.read_text().strip()
    parsed = json.loads(content)
    assert parsed["opp_id"] == "TEST-001"


def test_check_pg_caches_result():
    """PostgreSQL availability check should be cached."""
    from core.dual_writer import _check_pg
    import core.dual_writer as dw

    dw._pg_available = True
    assert _check_pg() is True

    dw._pg_available = False
    assert _check_pg() is False

    # Reset for other tests
    dw._pg_available = None
