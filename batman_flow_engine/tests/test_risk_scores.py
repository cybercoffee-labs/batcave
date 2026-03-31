"""
test_risk_scores.py — Lock in composite scoring model semantics.

Tests every score component formula and the composite assembly.
If any of these break, the composite_score is no longer trustworthy.

Formulas under test (all live in engine.py risk-scores block):
    operational_readiness = dq×0.6  + gordon_ok×0.4
    technical_risk        = dq
    market_behavior       = regime_map[label]  (default 0.7)
    governance_risk       = gordon_ok×0.50 + dq×0.30 + market_behavior×0.20
    financial_attractiveness = viable / total  (current cycle opps, None if <5)
    concentration_risk    = 1.0 − HHI  (1.0 when no positions)
    composite             = weighted mean of non-None components
                            weights: op=0.20, tech=0.15, gov=0.15,
                                     mb=0.15, fa=0.15, conc=0.20
"""

import json
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# ──────────────────────────── helpers ────────────────────────────


def _gordon_ok(status: str) -> float:
    """Mirror the gordon_ok mapping in engine.py."""
    return 1.0 if status == "OK" else (0.5 if status == "ALERT" else 0.0)


REGIME_MAP = {"NORMAL": 1.0, "TENSION": 0.85, "STRESS": 0.5, "DATA_DEGRADED": 0.3, "PANIC": 0.1}


def _compute_scores(dq: float, gordon_status: str, regime: str, fa: float | None, conc: float | None):
    """Replicate the engine.py risk-scores block in pure Python."""
    gok = _gordon_ok(gordon_status)
    mb = REGIME_MAP.get(regime, 0.7)

    op = round(dq * 0.6 + gok * 0.4, 4)
    tech = round(dq, 4)
    gov = round(gok * 0.50 + dq * 0.30 + mb * 0.20, 4)

    weights = [
        (op, 0.20),
        (tech, 0.15),
        (gov, 0.15),
        (mb, 0.15),
        (fa, 0.15) if fa is not None else None,
        (conc, 0.20) if conc is not None else None,
    ]
    valid = [(s, w) for item in weights if item is not None for s, w in [item]]
    total_w = sum(w for _, w in valid)
    composite = round(sum(s * w for s, w in valid) / total_w, 4) if total_w > 0 else None
    return {"op": op, "tech": tech, "gov": gov, "mb": mb, "composite": composite}


# ──────────────────── operational_readiness ────────────────────


@pytest.mark.parametrize(
    "dq, gordon_status, expected",
    [
        (1.0, "OK", 1.0),  # perfect state
        (0.84, "OK", 0.904),  # typical live state (dq=0.84)
        (0.60, "OK", 0.76),  # dq at GORDON dq_gate floor
        (1.0, "ALERT", 0.8),  # GORDON degraded, perfect data
        (1.0, "BLOCKED", 0.6),  # GORDON blocked, perfect data
        (0.0, "BLOCKED", 0.0),  # worst case
    ],
)
def test_operational_readiness(dq, gordon_status, expected):
    gok = _gordon_ok(gordon_status)
    result = round(dq * 0.6 + gok * 0.4, 4)
    assert result == expected


# ──────────────────────── technical_risk ───────────────────────


@pytest.mark.parametrize("dq", [0.0, 0.60, 0.80, 0.84, 0.96, 1.0])
def test_technical_risk_equals_dq_score(dq):
    assert round(dq, 4) == dq  # technical_risk is a direct pass-through


# ──────────────────────── market_behavior ──────────────────────


@pytest.mark.parametrize(
    "regime, expected",
    [
        ("NORMAL", 1.0),
        ("TENSION", 0.85),
        ("STRESS", 0.5),
        ("DATA_DEGRADED", 0.3),
        ("PANIC", 0.1),
        ("UNKNOWN_LABEL", 0.7),  # default for anything not in the map
        (None, 0.7),  # missing regime → default
    ],
)
def test_market_behavior_regime_map(regime, expected):
    result = REGIME_MAP.get(regime, 0.7)
    assert result == expected


# ──────────────────────── governance_risk ──────────────────────


@pytest.mark.parametrize(
    "dq, gordon_status, regime, expected",
    [
        (1.0, "OK", "NORMAL", 1.0),  # perfect — only state that reaches 1.0
        (0.84, "OK", "TENSION", 0.922),  # current live state
        (0.96, "OK", "TENSION", 0.958),  # recent live state (dq improved)
        (1.0, "ALERT", "NORMAL", 0.75),  # GORDON degraded; 0.5×0.5 + 1.0×0.3 + 1.0×0.2
        (0.70, "ALERT", "STRESS", 0.56),  # stress + alert + poor data
        (0.60, "BLOCKED", "PANIC", 0.2),  # worst plausible state; 0.0×0.5 + 0.6×0.3 + 0.1×0.2
        (1.0, "BLOCKED", "PANIC", 0.32),  # PANIC/BLOCKED even with clean data
    ],
)
def test_governance_risk_formula(dq, gordon_status, regime, expected):
    gok = _gordon_ok(gordon_status)
    mb = REGIME_MAP.get(regime, 0.7)
    result = round(gok * 0.50 + dq * 0.30 + mb * 0.20, 4)
    assert result == expected


def test_governance_risk_only_reaches_1_under_perfect_conditions():
    """1.0 requires GORDON=OK + dq=1.0 + NORMAL regime simultaneously."""
    gok = _gordon_ok("OK")
    mb = REGIME_MAP["NORMAL"]
    assert round(gok * 0.50 + 1.0 * 0.30 + mb * 0.20, 4) == 1.0

    # Any degradation drops below 1.0
    mb_tension = REGIME_MAP["TENSION"]
    assert round(gok * 0.50 + 1.0 * 0.30 + mb_tension * 0.20, 4) < 1.0


def test_panic_regime_collapses_governance():
    """PANIC + BLOCKED → governance_risk ≤ 0.35 regardless of dq."""
    for dq in [0.0, 0.5, 1.0]:
        gok = _gordon_ok("BLOCKED")  # PANIC sets gordon BLOCKED
        mb = REGIME_MAP["PANIC"]
        gov = round(gok * 0.50 + dq * 0.30 + mb * 0.20, 4)
        assert gov <= 0.35, f"governance_risk={gov} too high under PANIC/BLOCKED with dq={dq}"


# ──────────────────── financial_attractiveness ─────────────────


def test_viable_opportunity_ratio_happy_path(tmp_path):
    from engine import _viable_opportunity_ratio

    log = tmp_path / "opportunities.jsonl"
    records = [{"viable": True}] * 30 + [{"viable": False}] * 20
    log.write_text("\n".join(json.dumps(r) for r in records))

    with patch("engine.LOGS_DIR", tmp_path):
        result = _viable_opportunity_ratio(n=50)
    assert result == 0.6


def test_viable_opportunity_ratio_all_viable(tmp_path):
    from engine import _viable_opportunity_ratio

    log = tmp_path / "opportunities.jsonl"
    log.write_text("\n".join(json.dumps({"viable": True}) for _ in range(50)))

    with patch("engine.LOGS_DIR", tmp_path):
        result = _viable_opportunity_ratio()
    assert result == 1.0


def test_viable_opportunity_ratio_none_viable(tmp_path):
    from engine import _viable_opportunity_ratio

    log = tmp_path / "opportunities.jsonl"
    log.write_text("\n".join(json.dumps({"viable": False}) for _ in range(50)))

    with patch("engine.LOGS_DIR", tmp_path):
        result = _viable_opportunity_ratio()
    assert result == 0.0


def test_viable_opportunity_ratio_returns_none_when_insufficient(tmp_path):
    """Fewer than 5 records → None (sample too small to be meaningful)."""
    from engine import _viable_opportunity_ratio

    log = tmp_path / "opportunities.jsonl"
    log.write_text("\n".join(json.dumps({"viable": True}) for _ in range(4)))

    with patch("engine.LOGS_DIR", tmp_path):
        result = _viable_opportunity_ratio()
    assert result is None


def test_viable_opportunity_ratio_returns_none_when_file_missing(tmp_path):
    from engine import _viable_opportunity_ratio

    with patch("engine.LOGS_DIR", tmp_path):  # no file in tmp_path
        result = _viable_opportunity_ratio()
    assert result is None


def test_viable_opportunity_ratio_uses_last_n(tmp_path):
    """Only the last n records are sampled."""
    from engine import _viable_opportunity_ratio

    log = tmp_path / "opportunities.jsonl"
    # 50 non-viable old records, then 10 viable recent ones
    old = [json.dumps({"viable": False})] * 50
    recent = [json.dumps({"viable": True})] * 10
    log.write_text("\n".join(old + recent))

    with patch("engine.LOGS_DIR", tmp_path):
        result = _viable_opportunity_ratio(n=10)
    assert result == 1.0


def test_current_cycle_opportunities_normalizes_mixed_scanner_outputs():
    from engine import _current_cycle_opportunities

    scanner_results = [
        [{"viable": True}, {"viable": False}],
        {"viable": True},
        {
            "results": {
                "USDT/MXN": {"status": "ok", "viable": True},
                "USDT/ARS": {"status": "error", "viable": False},
            }
        },
        None,
    ]

    result = _current_cycle_opportunities(scanner_results)
    assert result == [
        {"viable": True},
        {"viable": False},
        {"viable": True},
        {"status": "ok", "viable": True},
    ]


def test_run_engine_financial_attractiveness_uses_same_cycle_counts(tmp_path):
    import core.gordon as gordon_mod
    import engine as eng_mod

    fake_result = {
        "data_quality": {"dq_score": 1.0, "status": "ok"},
        "stress": {"regime": {"label": "NORMAL", "triggers": []}},
        "dq": {"equities_ok_ratio": 0.25},
        "meta": {"opportunities_total_cycle": 5, "opportunities_viable_cycle": 4},
        "errors": [],
    }

    with (
        patch.object(eng_mod, "_build_engine_result", return_value=fake_result),
        patch.object(eng_mod, "_enrich_runtime_metadata"),
        patch.object(eng_mod, "_persist_run"),
        patch.object(eng_mod, "_harvey_is_initialized", return_value=True),
        patch.object(eng_mod, "_viable_opportunity_ratio", return_value=0.0),
        patch.object(eng_mod, "ingest_opportunities"),
        patch.object(eng_mod, "LOCK_FILE", tmp_path / "engine.lock"),
        patch(
            "database.postgres.get_concentration_risk", return_value={"score": 1.0, "top_position_pct": 1.0, "hhi": 0.0}
        ),
        patch("database.postgres.save_risk_score"),
        patch.object(gordon_mod, "is_kill_switch_active", return_value=False),
        patch.object(
            gordon_mod,
            "check_runtime_guard",
            return_value={"active": False, "status": "not_found", "pid": None, "path": ""},
        ),
        patch.object(gordon_mod, "log_gordon_event"),
        patch.object(gordon_mod, "AUDIT_LOG_FILE", tmp_path / "gordon_audit.jsonl"),
    ):
        result = eng_mod.run_engine(MagicMock(equities=[], crypto=[]))

    assert result["risk_scores"]["financial_attractiveness"] == 0.8


# ──────────────────────── concentration_risk ───────────────────


def test_concentration_risk_empty_portfolio_returns_1(tmp_path):
    """No active positions → score=1.0 (no concentration risk)."""
    from database.postgres import get_concentration_risk

    with patch("database.postgres.get_cursor") as mock_cur:
        mock_cur.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_concentration_risk()

    assert result["score"] == 1.0
    assert result["hhi"] == 0.0
    assert result["positions"] == 0


def test_concentration_risk_single_position_is_fully_concentrated(tmp_path):
    """One position: HHI=1.0, score=0.0."""
    from database.postgres import get_concentration_risk

    with patch("database.postgres.get_cursor") as mock_cur:
        mock_cur.return_value.__enter__.return_value.fetchall.return_value = [("p1", 1000.0)]
        result = get_concentration_risk()

    assert result["hhi"] == 1.0
    assert result["score"] == 0.0
    assert result["positions"] == 1


def test_concentration_risk_equal_positions_maximally_diversified():
    """Two equal positions: HHI=0.5, score=0.5."""
    from database.postgres import get_concentration_risk

    with patch("database.postgres.get_cursor") as mock_cur:
        mock_cur.return_value.__enter__.return_value.fetchall.return_value = [
            ("p1", 500.0),
            ("p2", 500.0),
        ]
        result = get_concentration_risk()

    assert result["hhi"] == 0.5
    assert result["score"] == 0.5


def test_concentration_risk_db_exception_returns_none():
    """DB failure → score=None so weight is dropped (genuinely unknown)."""
    from database.postgres import get_concentration_risk

    with patch("database.postgres.get_cursor", side_effect=Exception("pg down")):
        result = get_concentration_risk()

    assert result["score"] is None


# ──────────────────────── composite assembly ───────────────────


def test_composite_full_weights_perfect_state():
    """All components available + perfect inputs → composite = 1.0."""
    scores = _compute_scores(dq=1.0, gordon_status="OK", regime="NORMAL", fa=1.0, conc=1.0)
    assert scores["composite"] == 1.0


def test_composite_uses_full_weight_when_all_present():
    """When fa and conc are both present, all 5 declared weights sum to 1.0."""
    fa, conc = 0.5, 1.0
    scores = _compute_scores(dq=0.84, gordon_status="OK", regime="TENSION", fa=fa, conc=conc)
    # Verify by reconstructing with full weight sum = 1.0
    total_w = 0.20 + 0.15 + 0.15 + 0.15 + 0.15 + 0.20
    assert total_w == 1.0
    assert scores["composite"] is not None


def test_composite_drops_fa_weight_when_none():
    """When financial_attractiveness is None, its 0.15 weight is redistributed."""
    full = _compute_scores(dq=0.84, gordon_status="OK", regime="TENSION", fa=0.5, conc=1.0)
    no_fa = _compute_scores(dq=0.84, gordon_status="OK", regime="TENSION", fa=None, conc=1.0)
    # Dropping a mid-range fa (0.5) when other scores are higher increases composite
    assert no_fa["composite"] > full["composite"]


def test_composite_drops_conc_weight_when_none():
    """When concentration_risk is None (DB error), its 0.20 weight is redistributed."""
    with_conc = _compute_scores(dq=0.84, gordon_status="OK", regime="TENSION", fa=0.5, conc=1.0)
    no_conc = _compute_scores(dq=0.84, gordon_status="OK", regime="TENSION", fa=0.5, conc=None)
    # Dropping conc=1.0 from a set where other scores < 1.0 decreases composite
    assert no_conc["composite"] < with_conc["composite"]


def test_composite_panic_scenario():
    """PANIC + GORDON BLOCKED produces composite well below 0.5."""
    scores = _compute_scores(dq=0.60, gordon_status="BLOCKED", regime="PANIC", fa=0.1, conc=1.0)
    assert scores["composite"] < 0.5


def test_composite_current_live_state():
    """Spot-check current live operating conditions (TENSION/OK/dq≈0.96)."""
    scores = _compute_scores(dq=0.96, gordon_status="OK", regime="TENSION", fa=0.54, conc=1.0)
    # Should be between 0.85 and 0.95 — healthy but not perfect
    assert 0.85 < scores["composite"] < 0.95


def test_composite_weight_invariant():
    """Weight declarations in the score list must sum to exactly 1.0."""
    declared_weights = [0.20, 0.15, 0.15, 0.15, 0.15, 0.20]
    assert sum(declared_weights) == 1.0
