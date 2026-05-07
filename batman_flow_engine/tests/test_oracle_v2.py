"""Tests for Oracle V2 backtesting."""

from __future__ import annotations

import json


def test_backtester_run_and_report(tmp_path):
    from oracle_v2 import backtester as module
    from oracle_v2.backtester import Backtester

    log_file = tmp_path / "opportunities.jsonl"
    report_file = tmp_path / "backtest_results.json"
    rows = [
        {
            "opp_id": "1",
            "ts": "2026-04-13T10:00:00+00:00",
            "asset": "USDT",
            "market": "ARS",
            "scanner_id": "C-P2P-LATAM",
            "edge_net": 5.0,
        },
        {
            "opp_id": "2",
            "ts": "2026-04-13T11:00:00+00:00",
            "asset": "DOT",
            "market": "DOT",
            "scanner_id": "D-MULTI-EXCHANGE",
            "edge_net": 0.5,
        },
        {
            "opp_id": "3",
            "ts": "2026-04-14T11:00:00+00:00",
            "asset": "BTC",
            "route": "USDT-MXN->USDT-ARS",
            "scanner_id": "F-CROSS-CURRENCY",
            "edge_net": 2.0,
        },
    ]
    log_file.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    module.OPPORTUNITIES_FILE = log_file
    module.REPORT_FILE = report_file

    bt = Backtester(capital=1000.0)
    trades = bt.run(min_edge=1.0, max_trades_per_day=5)
    report = bt.generate_report()

    assert len(trades) == 2
    assert report["total_trades"] == 2
    assert report["winning_trades"] == 2
    assert report["profit_by_scanner"]["C-P2P-LATAM"] > 0
    assert report["profit_by_pair"]["USDT/ARS"] > 0
    assert report_file.exists()


def test_backtester_empty_log(tmp_path):
    from oracle_v2 import backtester as module
    from oracle_v2.backtester import Backtester

    module.OPPORTUNITIES_FILE = tmp_path / "missing.jsonl"
    module.REPORT_FILE = tmp_path / "backtest_results.json"

    bt = Backtester(capital=1000.0)
    bt.run(min_edge=1.0)
    report = bt.generate_report()

    assert report["total_trades"] == 0
    assert report["equity_curve"] == [1000.0]


def test_visualizer_handles_missing_matplotlib():
    from oracle_v2.visualizer import BacktestVisualizer

    report = {"equity_curve": [1000, 1010], "profit_by_scanner": {"A": 10}, "profit_by_hour": {"1": 2}}
    viz = BacktestVisualizer(report)
    assert isinstance(viz.generate_all(), list)
