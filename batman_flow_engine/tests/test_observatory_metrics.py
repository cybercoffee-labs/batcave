from datetime import UTC, datetime

from core.observatory import build_architecture_status
from tools.architecture_status import build_dashboard_payload


FIXTURE_RECORDS = [
    {
        "opp_id": "opp-1",
        "ts": "2026-03-11T00:00:00+00:00",
        "scanner_id": "C-P2P-LATAM",
        "asset": "USDT",
        "market": "MXN",
        "venue": "binance_p2p",
        "edge_net": 0.12,
        "depth_estimate": 10000,
        "merchant_count": 8,
        "viable": True,
    },
    {
        "opp_id": "opp-2",
        "ts": "2026-03-11T01:00:00+00:00",
        "scanner_id": "C-P2P-LATAM",
        "asset": "USDT",
        "market": "ARS",
        "venue": "binance_p2p",
        "edge_net": -0.05,
        "depth_estimate": 5000,
        "merchant_count": 6,
        "viable": False,
    },
    {
        "opp_id": "opp-3",
        "ts": "2026-03-11T02:30:00+00:00",
        "scanner_id": "B-FUNDING-BASIS",
        "asset": "BTC",
        "venue": "binance_spot_vs_futures",
        "basis_pct": -0.03,
    },
]


def test_observatory_snapshot_includes_graph_and_health_extensions(tmp_path):
    now = datetime(2026, 3, 11, 4, 0, tzinfo=UTC)

    snapshot = build_architecture_status(
        records=FIXTURE_RECORDS,
        db_path=tmp_path / "batman.db",
        latest_snapshot_path=tmp_path / "latest.json",
        reports_dir=tmp_path / "reports",
        opportunity_logs=(),
        candidate_paths=(),
        base_dir=tmp_path,
        now=now,
    )

    assert snapshot["summary"]["signals_total"] == 3
    assert snapshot["summary"]["graph_edges"] == 3
    assert "graph_summary" in snapshot
    assert "top_markets_by_flow" in snapshot
    assert "central_nodes" in snapshot
    assert snapshot["market_flow_summary"]["top_markets_by_flow"]
    assert snapshot["architecture"]["summary"]["missing"] >= 1
    assert snapshot["system_health"]["stale_signals"] is False


def test_observatory_handles_empty_records_gracefully(tmp_path):
    snapshot = build_architecture_status(
        records=[],
        db_path=tmp_path / "batman.db",
        latest_snapshot_path=tmp_path / "latest.json",
        reports_dir=tmp_path / "reports",
        opportunity_logs=(),
        candidate_paths=(),
        base_dir=tmp_path,
        now=datetime(2026, 3, 11, 4, 0, tzinfo=UTC),
    )

    assert snapshot["summary"]["signals_total"] == 0
    assert snapshot["graph_summary"]["edges_total"] == 0
    assert snapshot["top_markets_by_flow"] == []
    assert snapshot["central_nodes"] == []
    assert snapshot["harvey"]["signals_per_scanner"] == {}


def test_dashboard_payload_exposes_required_sections(tmp_path):
    snapshot = build_architecture_status(
        records=FIXTURE_RECORDS,
        db_path=tmp_path / "batman.db",
        latest_snapshot_path=tmp_path / "latest.json",
        reports_dir=tmp_path / "reports",
        opportunity_logs=(),
        candidate_paths=(),
        base_dir=tmp_path,
        now=datetime(2026, 3, 11, 4, 0, tzinfo=UTC),
    )
    payload = build_dashboard_payload(snapshot)

    assert "economic_graph" in payload
    assert "top_markets_by_flow" in payload
    assert "central_nodes" in payload
    assert "market_flow_summary" in payload
    assert payload["economic_graph"]["graph_summary"]["edges_total"] == 3
