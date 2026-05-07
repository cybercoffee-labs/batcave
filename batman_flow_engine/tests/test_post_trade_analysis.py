"""Tests for tools/post_trade_analysis.py (audit Section L.6).

Covers the three new public helpers (measure_slippage, attribution,
log_trade_analysis) plus the higher-level analyze_trade / run_daily_analysis
already in the module.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest


# ─────────────────────── measure_slippage ───────────────────────


def test_measure_slippage_buy_above_expected_is_adverse():
    """BUY paid more than expected → positive signed slippage = adverse."""
    from tools.post_trade_analysis import measure_slippage

    result = measure_slippage(expected_price=100.0, realized_price=100.5, fees=0.0)
    assert result["slippage_pct"] == pytest.approx(0.5)
    assert result["slippage_signed_pct"] == pytest.approx(0.5)
    assert result["friction_pct"] == 0.0
    assert result["effective_slippage_pct"] == pytest.approx(0.5)


def test_measure_slippage_buy_below_expected_is_favourable():
    """BUY paid less than expected → negative signed slippage."""
    from tools.post_trade_analysis import measure_slippage

    result = measure_slippage(expected_price=100.0, realized_price=99.5, fees=0.0)
    assert result["slippage_signed_pct"] == pytest.approx(-0.5)
    # Magnitude (slippage_pct) is always positive — the operator budgets
    # for the worst case regardless of direction this time.
    assert result["slippage_pct"] == pytest.approx(0.5)


def test_measure_slippage_includes_friction():
    from tools.post_trade_analysis import measure_slippage

    # 0.5% slippage + 0.10% friction (1 USD fee on 1000 USD trade) = 0.60% effective
    result = measure_slippage(
        expected_price=100.0,
        realized_price=100.5,
        fees=1.0,
        amount_usd=1000.0,
    )
    assert result["friction_pct"] == pytest.approx(0.1)
    assert result["effective_slippage_pct"] == pytest.approx(0.6)


def test_measure_slippage_zero_amount_yields_zero_friction():
    from tools.post_trade_analysis import measure_slippage

    result = measure_slippage(expected_price=100.0, realized_price=100.0, fees=5.0, amount_usd=0)
    assert result["friction_pct"] == 0.0


def test_measure_slippage_zero_expected_returns_zeros():
    """Defensive: expected_price=0 must not divide-by-zero."""
    from tools.post_trade_analysis import measure_slippage

    result = measure_slippage(expected_price=0, realized_price=18.0)
    assert result["slippage_pct"] == 0.0
    assert result["effective_slippage_pct"] == 0.0


def test_measure_slippage_handles_non_numeric_input():
    from tools.post_trade_analysis import measure_slippage

    result = measure_slippage(expected_price="oops", realized_price=18.0)  # type: ignore[arg-type]
    # Treated as zero — never raises.
    assert result["slippage_pct"] == 0.0


def test_measure_slippage_realised_none_treated_as_no_movement():
    from tools.post_trade_analysis import measure_slippage

    result = measure_slippage(expected_price=18.0, realized_price=None)  # type: ignore[arg-type]
    assert result["slippage_pct"] == 0.0
    assert result["slippage_signed_pct"] == 0.0


# ─────────────────────── attribution ───────────────────────


def test_attribution_profitable_classification():
    """Edge 1.0%, friction 0.1%, slippage 0.0% → net +0.9% → PROFITABLE."""
    from tools.post_trade_analysis import attribution

    result = attribution(edge_net=1.0, fees=0.1, slippage=0.0)
    assert result["net_pnl_pct"] == pytest.approx(0.9)
    assert result["classification"] == "PROFITABLE"


def test_attribution_breakeven_classification():
    """Edge 0.5%, friction 0.1%, slippage 0.2% → net +0.2% → BREAKEVEN."""
    from tools.post_trade_analysis import attribution

    result = attribution(edge_net=0.5, fees=0.1, slippage=0.2)
    assert result["net_pnl_pct"] == pytest.approx(0.2)
    assert result["classification"] == "BREAKEVEN"


def test_attribution_loss_classification():
    """Edge 0.3%, friction 0.4%, slippage 0.5% → net -0.6% → LOSS."""
    from tools.post_trade_analysis import attribution

    result = attribution(edge_net=0.3, fees=0.4, slippage=0.5)
    assert result["net_pnl_pct"] == pytest.approx(-0.6)
    assert result["classification"] == "LOSS"


def test_attribution_breakdown_signs():
    """Edge contributes positive; friction and slippage contribute negative."""
    from tools.post_trade_analysis import attribution

    result = attribution(edge_net=1.0, fees=0.1, slippage=0.2)
    bd = result["breakdown"]
    assert bd["edge_contribution"] == pytest.approx(1.0)
    assert bd["friction_loss"] == pytest.approx(-0.1)
    assert bd["slippage_loss"] == pytest.approx(-0.2)
    assert bd["net"] == pytest.approx(0.7)


def test_attribution_signed_slippage_treated_as_magnitude():
    """attribution must take ABS(slippage) so favourable price moves don't
    inflate the net P&L (the fill is only the entry; we haven't closed
    the trade yet)."""
    from tools.post_trade_analysis import attribution

    # Negative slippage (favourable BUY) should still be treated as a cost.
    fav = attribution(edge_net=1.0, fees=0.1, slippage=-0.3)
    adv = attribution(edge_net=1.0, fees=0.1, slippage=+0.3)
    assert fav["net_pnl_pct"] == adv["net_pnl_pct"]


def test_attribution_returns_usd_when_amount_provided():
    from tools.post_trade_analysis import attribution

    # Net = 0.5%, on $1000 = $5.00
    result = attribution(edge_net=0.7, fees=0.1, slippage=0.1, amount_usd=1000.0)
    assert result["net_pnl_usd"] == pytest.approx(5.0)
    assert result["amount_usd"] == 1000.0


def test_attribution_no_usd_field_when_amount_missing():
    from tools.post_trade_analysis import attribution

    result = attribution(edge_net=0.5, fees=0.1, slippage=0.1)
    assert "net_pnl_usd" not in result


def test_attribution_handles_non_numeric_input():
    from tools.post_trade_analysis import attribution

    result = attribution(edge_net="bad", fees=0.1, slippage=0.0)  # type: ignore[arg-type]
    assert result["classification"] == "ERROR"


# ─────────────────────── log_trade_analysis ───────────────────────


@pytest.fixture
def _persistence_paths(tmp_path, monkeypatch):
    """Redirect both JSONL and SQLite outputs to tmp."""
    import tools.post_trade_analysis as pta

    jsonl_p = tmp_path / "post_trade_analysis.jsonl"
    sqlite_p = tmp_path / "batman.db"
    monkeypatch.setattr(pta, "ANALYSIS_JSONL", jsonl_p)
    monkeypatch.setattr(pta, "ANALYSIS_SQLITE", sqlite_p)
    return jsonl_p, sqlite_p


def test_log_trade_analysis_writes_to_jsonl_and_sqlite(_persistence_paths):
    from tools.post_trade_analysis import attribution, log_trade_analysis

    jsonl_p, sqlite_p = _persistence_paths

    trade = {
        "intent_id": "INTENT-P2P-ABC123",
        "opp_id": "OPP-C-DEADBEEF",
        "cycle_id": "abcdef123456",
        "fiat": "MXN",
        "asset": "USDT",
        "side": "BUY",
        "expected_price": 18.05,
        "filled_price": 18.07,
        "filled_amount_usd": 500.0,
        "fees_usd": 0.5,
        "filled_ts": "2026-05-04T10:00:00+00:00",
    }
    analysis = attribution(edge_net=0.7, fees=0.1, slippage=0.111, amount_usd=500.0)

    result = log_trade_analysis(trade, analysis)
    assert result == {"jsonl_ok": True, "sqlite_ok": True}

    # JSONL roundtrip
    lines = [ln for ln in jsonl_p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["trade_id"] == "INTENT-P2P-ABC123"
    assert rec["opp_id"] == "OPP-C-DEADBEEF"
    assert rec["cycle_id"] == "abcdef123456"
    assert rec["classification"] == analysis["classification"]
    assert rec["edge_pct"] == 0.7
    assert rec["fiat"] == "MXN"

    # SQLite roundtrip
    with sqlite3.connect(sqlite_p) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(post_trade_analysis)").fetchall()}
        assert "trade_id" in cols
        assert "cycle_id" in cols
        rows = conn.execute(
            "SELECT trade_id, opp_id, classification, edge_pct, net_pnl_pct, fiat FROM post_trade_analysis"
        ).fetchall()
    assert len(rows) == 1
    trade_id, opp_id, classification, edge_pct, net_pnl_pct, fiat = rows[0]
    assert trade_id == "INTENT-P2P-ABC123"
    assert opp_id == "OPP-C-DEADBEEF"
    assert classification == analysis["classification"]
    assert edge_pct == pytest.approx(0.7)
    assert fiat == "MXN"


def test_log_trade_analysis_falls_back_to_unknown_id(_persistence_paths):
    """If the trade has no intent_id/opp_id/trade_id, store 'unknown' (not crash)."""
    from tools.post_trade_analysis import log_trade_analysis

    result = log_trade_analysis({}, {"classification": "BREAKEVEN"})
    assert result["jsonl_ok"] is True
    assert result["sqlite_ok"] is True
    jsonl_p, _ = _persistence_paths
    rec = json.loads(jsonl_p.read_text(encoding="utf-8").strip())
    assert rec["trade_id"] == "unknown"


def test_log_trade_analysis_jsonl_failure_does_not_block_sqlite(_persistence_paths, monkeypatch):
    from tools.post_trade_analysis import log_trade_analysis

    jsonl_p, sqlite_p = _persistence_paths

    # Make the JSONL parent unwritable by pointing at a path inside a file.
    bad_parent = jsonl_p.parent / "blocker"
    bad_parent.write_text("I am a file, not a dir", encoding="utf-8")
    bad_jsonl = bad_parent / "x.jsonl"

    result = log_trade_analysis(
        {"intent_id": "X"},
        {"classification": "BREAKEVEN", "net_pnl_pct": 0.0},
        jsonl_path=bad_jsonl,
        sqlite_path=sqlite_p,
    )
    assert result["jsonl_ok"] is False
    assert result["sqlite_ok"] is True


def test_log_trade_analysis_creates_idx_on_classification(_persistence_paths):
    """The dashboard wants to filter by classification fast — ensure the
    index exists after the first write."""
    from tools.post_trade_analysis import log_trade_analysis

    log_trade_analysis(
        {"intent_id": "Y"},
        {"classification": "PROFITABLE", "net_pnl_pct": 1.0},
    )
    _, sqlite_p = _persistence_paths
    with sqlite3.connect(sqlite_p) as conn:
        idxs = {row[1] for row in conn.execute("PRAGMA index_list(post_trade_analysis)").fetchall()}
    assert "idx_pta_classification" in idxs


# ─────────────────────── analyze_trade integration ───────────────────────


def test_analyze_trade_full_pnl_decomposition():
    """End-to-end: feed a closed trade dict, get edge/slip/fric/net + class."""
    from tools.post_trade_analysis import analyze_trade

    trade = {
        "intent_id": "INTENT-P2P-001",
        "expected_price": 100.0,
        "filled_price": 100.5,  # +0.5% slippage
        "filled_amount_usd": 1000.0,  # 1000 USD
        "fees_usd": 1.0,  # 0.1% friction
        "edge_net": 1.0,  # 1.0% expected edge
    }
    out = analyze_trade(trade)
    assert out["expected_edge_pct"] == pytest.approx(1.0)
    assert out["realized_slippage_pct"] == pytest.approx(0.5)
    assert out["friction_pct"] == pytest.approx(0.1)
    # net = 1.0 - 0.1 - |0.5| = 0.4 → BREAKEVEN
    assert out["net_pnl_pct"] == pytest.approx(0.4)
    assert out["classification"] == "BREAKEVEN"


def test_analyze_trade_returns_error_on_missing_fields():
    from tools.post_trade_analysis import analyze_trade

    out = analyze_trade({"opp_id": "X"})  # no prices, no edge
    assert out["classification"] == "ERROR"
    assert "error" in out


# ─────────────────────── run_daily_analysis ───────────────────────


def test_run_daily_analysis_aggregates_filled_orders(tmp_path):
    """Two filled trades for today → totals + averages match."""
    from tools.post_trade_analysis import run_daily_analysis

    today = datetime.now(timezone.utc).date().isoformat()
    ledger = tmp_path / "trades.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "intent_id": "T1",
            "expected_price": 100.0,
            "filled_price": 100.5,
            "filled_amount_usd": 1000.0,
            "fees_usd": 1.0,
            "edge_net": 1.0,
            "filled_ts": f"{today}T10:00:00+00:00",
        },
        {
            "intent_id": "T2",
            "expected_price": 200.0,
            "filled_price": 199.0,
            "filled_amount_usd": 2000.0,
            "fees_usd": 2.0,
            "edge_net": 0.5,
            "filled_ts": f"{today}T11:00:00+00:00",
        },
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    report = run_daily_analysis(date_iso=today, sources=[ledger])
    assert report["total_trades"] == 2
    # T1: 1.0 - 0.1 - 0.5 = 0.4 (BREAKEVEN)
    # T2: 0.5 - 0.1 - 0.5 = -0.1 (BREAKEVEN)
    assert report["breakeven"] == 2
    assert report["profitable"] == 0
    assert report["loss"] == 0


def test_run_daily_analysis_skips_unfilled_paper_rows(tmp_path):
    """PAPER trades with action=SIMULATED_TRADE have no filled_price → excluded."""
    from tools.post_trade_analysis import run_daily_analysis

    today = datetime.now(timezone.utc).date().isoformat()
    ledger = tmp_path / "trades.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "intent_id": "T-PAPER",
            "expected_price": 100.0,
            "executed_amount_usd": 500.0,
            "edge_net": 0.7,
            "filled_ts": f"{today}T10:00:00+00:00",
            # No filled_price → not "closed" by our definition.
        },
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    report = run_daily_analysis(date_iso=today, sources=[ledger])
    assert report["total_trades"] == 0


def test_run_daily_analysis_ignores_other_dates(tmp_path):
    from tools.post_trade_analysis import run_daily_analysis

    today = datetime.now(timezone.utc).date().isoformat()
    ledger = tmp_path / "trades.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "intent_id": "OLD",
                "expected_price": 100,
                "filled_price": 101,
                "filled_amount_usd": 100,
                "fees_usd": 0.1,
                "edge_net": 0.5,
                "filled_ts": "2024-01-01T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = run_daily_analysis(date_iso=today, sources=[ledger])
    assert report["total_trades"] == 0


def test_run_daily_analysis_handles_missing_ledger(tmp_path):
    from tools.post_trade_analysis import run_daily_analysis

    report = run_daily_analysis(sources=[tmp_path / "does-not-exist.jsonl"])
    assert report["total_trades"] == 0
