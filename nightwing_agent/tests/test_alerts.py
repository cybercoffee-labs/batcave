import json
from pathlib import Path

from alerts import _lucius_approved, collect_alerts, load_alert_records, render_alert_report
from dashboard import normalize_record


def test_load_alert_records_uses_latest_rows_and_skips_invalid_lines(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"cycle": 1, "decision": "PASS"}),
                "not-json",
                json.dumps(["not", "an", "object"]),
                json.dumps({"cycle": 2, "decision": "OPPORTUNITY"}),
                json.dumps({"cycle": 3, "decision": "PASS"}),
            ]
        ),
        encoding="utf-8",
    )

    records = load_alert_records(path=path, latest_n=2)

    assert [record["cycle"] for record in records] == [3, 2]


def test_collect_alerts_detects_required_conditions_and_legacy_execution():
    records = load_alert_records_from_objects(
        [
            {
                "cycle": 4,
                "ts": "2026-03-10T10:20:00+00:00",
                "mode": "SIMULATED",
                "decision": "OPPORTUNITY",
                "action": "SIMULATED_TRADE",
                "amount_usd": 50.0,
                "edge_net": 0.4,
                "lucius": {"approved": False},
                "batman": {"status": "stale", "opp_id": "OPP-4"},
            },
            {
                "cycle": 3,
                "ts": "2026-03-10T10:15:00+00:00",
                "mode": "PAPER",
                "decision": "PASS",
                "edge_net": -0.1,
                "batman": {"status": "ok", "opp_id": "OPP-3"},
            },
        ]
    )

    alerts = collect_alerts(records, edge_threshold=0.1)

    assert [record["cycle"] for record in alerts["opportunity"]] == [4]
    assert [record["cycle"] for record in alerts["batman_stale"]] == [4]
    assert [record["cycle"] for record in alerts["edge_positive"]] == [4]
    assert [record["cycle"] for record in alerts["executed_amount"]] == [4]
    assert [record["cycle"] for record in alerts["lucius_unapproved"]] == [4]


def test_collect_alerts_respects_threshold_and_optional_lucius_flag():
    records = load_alert_records_from_objects(
        [
            {
                "cycle": 5,
                "ts": "2026-03-10T10:25:00+00:00",
                "mode": "SIMULATED",
                "decision": "PASS",
                "edge_net": 0.05,
                "lucius": {"approved": False},
                "batman": {"status": "ok", "opp_id": "OPP-5"},
            }
        ]
    )

    alerts = collect_alerts(records, edge_threshold=0.1, include_lucius_unapproved=False)

    assert alerts["edge_positive"] == []
    assert alerts["lucius_unapproved"] == []


def test_render_alert_report_groups_findings_human_readably():
    records = load_alert_records_from_objects(
        [
            {
                "cycle": 6,
                "ts": "2026-03-10T10:30:00+00:00",
                "mode": "SIMULATED",
                "decision": "OPPORTUNITY",
                "edge_net": 0.2,
                "batman": {"status": "stale", "opp_id": "OPP-6"},
            }
        ]
    )
    alerts = collect_alerts(records)

    report = render_alert_report(alerts, rows_scanned=len(records), edge_threshold=0.0)

    assert "Nightwing alerts from latest 1 record(s)" in report
    assert "OPPORTUNITY decisions: 1" in report
    assert "Batman stale: 1" in report
    assert "edge_net > 0: 1" in report
    assert "ts=2026-03-10T10:30:00+00:00" in report
    assert "cycle=6" in report
    assert "opp_id=OPP-6" in report


def load_alert_records_from_objects(records: list[dict]) -> list[dict]:
    normalized = []
    for record in records:
        line = json.dumps(record)
        loaded = json.loads(line)
        normalized_record = normalize_record(loaded)
        normalized_record["lucius.approved"] = _lucius_approved(loaded)
        normalized.append(normalized_record)
    return normalized
