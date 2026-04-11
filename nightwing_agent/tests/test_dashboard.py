import json
from pathlib import Path

from dashboard import apply_filters, build_summary, load_records, normalize_record, render_html


def test_load_records_newest_first_and_skip_invalid_json(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"cycle": 1, "ts": "2026-03-10T10:00:00+00:00", "mode": "SIMULATED"}),
                "{invalid json",
                json.dumps({"cycle": 2, "ts": "2026-03-10T10:05:00+00:00", "mode": "PAPER"}),
            ]
        ),
        encoding="utf-8",
    )

    records = load_records(path)

    assert [record["cycle"] for record in records] == [2, 1]


def test_normalize_record_uses_legacy_fallbacks():
    record = {
        "cycle": 1,
        "ts": "2026-03-10T10:00:00+00:00",
        "mode": "PAPER",
        "decision": "OPPORTUNITY",
        "action": "SIMULATED_TRADE",
        "amount_usd": 500.0,
        "edge_net": 0.44,
        "lucius": {"daily_exposure_usd": 1500.0},
        "batman": {
            "status": "stale",
            "age_seconds": 321.0,
            "data": {"opp_id": "OPP-123"},
        },
    }

    normalized = normalize_record(record)

    assert normalized["evaluated_amount_usd"] == 500.0
    assert normalized["executed_amount_usd"] == 500.0
    assert normalized["action"] == "SIMULATED_TRADE"
    assert normalized["execution_state"] == "simulated_trade"
    assert normalized["record_version"] == "legacy"
    assert normalized["edge_sign"] == "positive"
    assert normalized["lucius.daily_exposure_usd"] == 1500.0
    assert normalized["batman.status"] == "stale"
    assert normalized["batman.age_seconds"] == 321.0
    assert normalized["batman.freshness"] == "stale"
    assert normalized["batman.opp_id"] == "OPP-123"


def test_normalize_record_defaults_for_missing_pass_action():
    normalized = normalize_record(
        {
            "cycle": 3,
            "ts": "2026-03-10T10:10:00+00:00",
            "mode": "SIMULATED",
            "decision": "PASS",
            "edge_net": -0.2,
        }
    )

    assert normalized["action"] == "NO_ACTION"
    assert normalized["execution_state"] == "no_execution"
    assert normalized["record_version"] == "legacy"
    assert normalized["evaluated_amount_usd"] is None
    assert normalized["executed_amount_usd"] == 0
    assert normalized["edge_sign"] == "negative"
    assert normalized["batman.status"] == "missing"
    assert normalized["batman.age_seconds"] is None
    assert normalized["batman.freshness"] == "unknown"
    assert normalized["batman.opp_id"] is None


def test_normalize_record_defaults_for_missing_blocked_action():
    normalized = normalize_record(
        {
            "cycle": 4,
            "ts": "2026-03-10T10:15:00+00:00",
            "mode": "PAPER",
            "decision": "BLOCKED_COMPLIANCE",
            "edge_net": 0.0,
        }
    )

    assert normalized["action"] == "BLOCKED"
    assert normalized["execution_state"] == "blocked"
    assert normalized["edge_sign"] == "zero"


def test_normalize_record_marks_current_row_when_amount_fields_exist():
    normalized = normalize_record(
        {
            "cycle": 5,
            "ts": "2026-03-10T10:20:00+00:00",
            "mode": "PAPER",
            "decision": "OPPORTUNITY",
            "action": "SIMULATED_TRADE",
            "edge_net": 1.2,
            "evaluated_amount_usd": 800.0,
            "executed_amount_usd": 750.0,
            "batman": {"status": "ok", "age_seconds": 45.0, "opp_id": "OPP-NEW"},
        }
    )

    assert normalized["record_version"] == "current"
    assert normalized["batman.freshness"] == "fresh"


def test_normalize_record_marks_logged_only_execution_state():
    normalized = normalize_record(
        {
            "cycle": 9,
            "ts": "2026-03-10T10:21:00+00:00",
            "mode": "SIMULATED",
            "decision": "PASS",
            "action": "LOGGED",
            "edge_net": 0.1,
        }
    )

    assert normalized["execution_state"] == "logged_only"


def test_normalize_record_uses_stale_batman_opp_id_fallback():
    normalized = normalize_record(
        {
            "cycle": 6,
            "ts": "2026-03-10T10:25:00+00:00",
            "mode": "SIMULATED",
            "decision": "PASS",
            "batman": {
                "status": "stale",
                "age_seconds": 180.0,
                "opp_id": None,
                "data": {"opp_id": "OPP-FALLBACK"},
            },
        }
    )

    assert normalized["batman.opp_id"] == "OPP-FALLBACK"
    assert normalized["batman.freshness"] == "aging"


def test_apply_filters_and_summary_use_newest_first_records():
    records = [
        normalize_record(
            {
                "cycle": 3,
                "ts": "2026-03-10T10:10:00+00:00",
                "mode": "SIMULATED",
                "decision": "PASS",
                "action": "LOGGED",
                "edge_net": -0.9,
                "lucius": {"daily_exposure_usd": 2000.0},
                "batman": {"status": "ok", "age_seconds": 25.0, "opp_id": "NEW"},
            }
        ),
        normalize_record(
            {
                "cycle": 2,
                "ts": "2026-03-10T10:05:00+00:00",
                "mode": "PAPER",
                "decision": "OPPORTUNITY",
                "action": "SIMULATED_TRADE",
                "edge_net": 0.5,
                "lucius": {"daily_exposure_usd": 1500.0},
                "batman": {"status": "ok", "age_seconds": 40.0, "opp_id": "MID"},
            }
        ),
        normalize_record(
            {
                "cycle": 1,
                "ts": "2026-03-10T10:00:00+00:00",
                "mode": "SIMULATED",
                "decision": "BLOCKED_COMPLIANCE",
                "action": "BLOCKED",
                "edge_net": 0.1,
                "lucius": {"daily_exposure_usd": 0.0},
                "batman": {"status": "missing", "age_seconds": None, "opp_id": None},
            }
        ),
    ]

    filtered = apply_filters(records, mode="SIMULATED", decision="", latest_n=1)
    summary = build_summary(filtered)

    assert len(filtered) == 1
    assert filtered[0]["cycle"] == 3
    assert summary["total_records"] == 1
    assert summary["count_pass"] == 1
    assert summary["count_opportunity"] == 0
    assert summary["count_blocked_compliance"] == 0
    assert summary["count_legacy"] == 1
    assert summary["count_batman_stale"] == 0
    assert summary["count_edge_positive"] == 0
    assert summary["count_edge_negative"] == 1
    assert summary["avg_edge_net"] == -0.9
    assert summary["max_edge_net"] == -0.9
    assert summary["min_edge_net"] == -0.9
    assert summary["latest_daily_exposure_usd"] == 2000.0
    assert summary["latest_batman_age_seconds"] == 25.0


def test_load_records_skips_invalid_json_lines_and_non_objects(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"cycle": 1}),
                "not-json",
                json.dumps(["not", "an", "object"]),
                json.dumps({"cycle": 2}),
            ]
        ),
        encoding="utf-8",
    )

    records = load_records(path)

    assert [record["cycle"] for record in records] == [2, 1]


def test_build_summary_uses_filtered_records_only():
    records = [
        normalize_record(
            {
                "cycle": 7,
                "ts": "2026-03-10T10:30:00+00:00",
                "mode": "SIMULATED",
                "decision": "PASS",
                "edge_net": -0.1,
            }
        ),
        normalize_record(
            {
                "cycle": 6,
                "ts": "2026-03-10T10:25:00+00:00",
                "mode": "SIMULATED",
                "decision": "BLOCKED_COMPLIANCE",
                "edge_net": 0.0,
            }
        ),
        normalize_record(
            {
                "cycle": 5,
                "ts": "2026-03-10T10:20:00+00:00",
                "mode": "PAPER",
                "decision": "OPPORTUNITY",
                "action": "SIMULATED_TRADE",
                "amount_usd": 50.0,
                "edge_net": 0.2,
                "lucius": {"daily_exposure_usd": 99.0},
                "batman": {"status": "ok", "age_seconds": 10.0, "opp_id": "OPP-5"},
            }
        ),
    ]

    filtered = apply_filters(records, mode="SIMULATED", decision="BLOCKED_COMPLIANCE", latest_n=10)
    summary = build_summary(filtered)

    assert [record["cycle"] for record in filtered] == [6]
    assert summary == {
        "total_records": 1,
        "count_pass": 0,
        "count_opportunity": 0,
        "count_blocked_compliance": 1,
        "count_legacy": 1,
        "count_batman_stale": 0,
        "count_edge_positive": 0,
        "count_edge_negative": 0,
        "avg_edge_net": 0.0,
        "max_edge_net": 0.0,
        "min_edge_net": 0.0,
        "latest_daily_exposure_usd": None,
        "latest_batman_age_seconds": None,
    }


def test_apply_filters_supports_combined_operator_filters():
    records = [
        normalize_record(
            {
                "cycle": 10,
                "ts": "2026-03-10T10:40:00+00:00",
                "mode": "SIMULATED",
                "decision": "PASS",
                "edge_net": -0.4,
                "batman": {"status": "stale", "age_seconds": 301.0},
            }
        ),
        normalize_record(
            {
                "cycle": 9,
                "ts": "2026-03-10T10:35:00+00:00",
                "mode": "SIMULATED",
                "decision": "PASS",
                "edge_net": 0.3,
                "batman": {"status": "stale", "age_seconds": 302.0},
                "evaluated_amount_usd": 100.0,
                "executed_amount_usd": 0.0,
            }
        ),
        normalize_record(
            {
                "cycle": 8,
                "ts": "2026-03-10T10:30:00+00:00",
                "mode": "PAPER",
                "decision": "OPPORTUNITY",
                "action": "SIMULATED_TRADE",
                "edge_net": 0.5,
                "batman": {"status": "ok", "age_seconds": 15.0},
            }
        ),
    ]

    filtered = apply_filters(
        records,
        mode="SIMULATED",
        decision="PASS",
        batman_status="stale",
        edge_sign="negative",
        legacy_only=True,
        stale_only=True,
        latest_n=10,
    )

    assert [record["cycle"] for record in filtered] == [10]


def test_render_html_shows_operational_indicators():
    records = [
        normalize_record(
            {
                "cycle": 8,
                "ts": "2026-03-10T10:35:00+00:00",
                "mode": "SIMULATED",
                "decision": "PASS",
                "edge_net": -0.3,
                "batman": {"status": "stale", "age_seconds": 301.0},
            }
        )
    ]
    summary = build_summary(records)

    content = render_html(
        records,
        summary,
        mode="",
        decision="",
        batman_status="",
        edge_sign="",
        legacy_only=False,
        stale_only=False,
        latest_n=100,
        mode_options=["SIMULATED"],
        decision_options=["PASS"],
        batman_status_options=["stale"],
        edge_sign_options=["negative"],
    )

    assert "NO_ACTION" in content
    assert "execution_state" in content
    assert "legacy" in content
    assert "pre-refactor exposure semantics" in content
    assert 'class="status-stale"' in content
    assert "negative" in content
    assert "legacy only" in content
    assert "stale only" in content
