import json

from core.economic_graph import build_graph
from core.economic_graph import compute_centrality
from core.economic_graph import compute_flow_scores
from core.economic_graph import export_graph_json


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
        "observe_only": True,
    },
    {
        "opp_id": "opp-2",
        "ts": "2026-03-11T01:00:00+00:00",
        "scanner_id": "C-P2P-LATAM",
        "asset": "USDT",
        "market": "MXN",
        "venue": "binance_p2p",
        "edge_net": 0.18,
        "depth_estimate": 20000,
        "merchant_count": 10,
        "viable": True,
        "observe_only": True,
    },
    {
        "opp_id": "opp-3",
        "ts": "2026-03-11T02:00:00+00:00",
        "scanner_id": "C-P2P-LATAM",
        "asset": "USDT",
        "market": "ARS",
        "venue": "binance_p2p",
        "edge_net": -0.05,
        "depth_estimate": 5000,
        "merchant_count": 6,
        "viable": False,
        "observe_only": True,
    },
    {
        "opp_id": "opp-4",
        "ts": "2026-03-11T03:00:00+00:00",
        "scanner_id": "B-FUNDING-BASIS",
        "asset": "BTC",
        "venue": "binance_spot_vs_futures",
        "basis_pct": -0.03,
        "observe_only": True,
    },
]


def test_compute_flow_scores_uses_required_formula():
    scored = compute_flow_scores(
        [
            {
                "avg_edge_net": 0.2,
                "avg_depth_estimate": 12000,
            }
        ]
    )

    assert scored[0]["flow_score"] == 2.4


def test_build_graph_aggregates_edges_and_summary():
    graph = build_graph(records=FIXTURE_RECORDS)

    assert graph["summary"]["nodes_total"] == 5
    assert graph["summary"]["edges_total"] == 3
    assert graph["summary"]["signals_considered"] == 4

    mxn_edge = next(edge for edge in graph["edges"] if edge["market"] == "MXN")
    assert mxn_edge["avg_edge_net"] == 0.15
    assert mxn_edge["avg_depth_estimate"] == 15000.0
    assert mxn_edge["viable_pct"] == 100.0
    assert mxn_edge["merchant_count"] == 9.0
    assert mxn_edge["flow_score"] == 2.25


def test_compute_centrality_ranks_market_hubs():
    graph = build_graph(records=FIXTURE_RECORDS)
    centrality = compute_centrality(graph)

    assert centrality["liquidity_hubs"][0]["label"] == "MXN"
    assert centrality["central_nodes"][0]["label"] == "USDT"


def test_export_graph_json_is_machine_readable_and_stable():
    graph_json = export_graph_json(records=FIXTURE_RECORDS)
    payload = json.loads(graph_json)

    assert list(payload.keys()) == ["centrality", "edges", "nodes", "summary"]
    assert payload["nodes"][0]["id"].startswith("currency:")
    assert any(edge["scanner_id"] == "C-P2P-LATAM" for edge in payload["edges"])
