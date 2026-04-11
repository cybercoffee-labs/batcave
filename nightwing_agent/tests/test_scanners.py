import json
from pathlib import Path

from scanners.opportunity_scanner import (
    append_events as append_opportunity_events,
    collect_opportunity_events,
    load_scanner_records as load_opportunity_records,
    render_summary as render_opportunity_summary,
)
from scanners.system_scanner import (
    append_events as append_system_events,
    collect_system_events,
    load_scanner_records as load_system_records,
    render_summary as render_system_summary,
)


def test_opportunity_scanner_loads_latest_rows_and_skips_invalid_lines(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"cycle": 1, "decision": "PASS"}),
                "not-json",
                json.dumps(["not", "an", "object"]),
                json.dumps({"cycle": 2, "decision": "OPPORTUNITY", "edge_net": 0.2}),
                json.dumps({"cycle": 3, "decision": "PASS"}),
            ]
        ),
        encoding="utf-8",
    )

    records = load_opportunity_records(path=path, latest_n=2)

    assert [record["cycle"] for record in records] == [3, 2]


def test_opportunity_scanner_detects_and_appends_events(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    events_path = tmp_path / "scanner_events.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "cycle": 2,
                        "ts": "2026-03-10T10:10:00+00:00",
                        "mode": "SIMULATED",
                        "decision": "OPPORTUNITY",
                        "edge_net": 0.25,
                        "batman": {"status": "ok", "opp_id": "OPP-2"},
                    }
                ),
                json.dumps(
                    {
                        "cycle": 1,
                        "ts": "2026-03-10T10:05:00+00:00",
                        "mode": "PAPER",
                        "decision": "PASS",
                        "edge_net": 0.30,
                        "batman": {"status": "ok", "opp_id": "OPP-1"},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    records = load_opportunity_records(path=path, latest_n=10)
    grouped = collect_opportunity_events(records, edge_threshold=0.2)
    appended = append_opportunity_events(events_path, grouped)
    report = render_opportunity_summary(grouped, rows_scanned=len(records), edge_threshold=0.2)

    assert [event["cycle"] for event in grouped["opportunity_decision"]] == [2]
    assert [event["cycle"] for event in grouped["edge_threshold"]] == [1, 2]
    assert [event["cycle"] for event in grouped["viable_opportunity"]] == [2]
    assert appended == 4
    assert "viable opportunities: 1" in report
    assert "opp_id=OPP-2" in report
    written = events_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(written) == 4


def test_system_scanner_detects_and_appends_events(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    events_path = tmp_path / "system_events.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "cycle": 3,
                        "ts": "2026-03-10T10:15:00+00:00",
                        "mode": "SIMULATED",
                        "decision": "PASS",
                        "edge_net": -0.1,
                        "lucius": {"approved": False},
                        "batman": {"status": "stale", "age_seconds": 450.0, "opp_id": "OPP-3"},
                    }
                ),
                json.dumps(
                    {
                        "cycle": 2,
                        "ts": "2026-03-10T10:10:00+00:00",
                        "mode": "PAPER",
                        "decision": "PASS",
                        "edge_net": 0.1,
                        "batman": {"status": "ok", "age_seconds": 40.0, "opp_id": "OPP-2"},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    records = load_system_records(path=path, latest_n=10)
    grouped = collect_system_events(records, age_threshold=300.0)
    appended = append_system_events(events_path, grouped)
    report = render_system_summary(grouped, rows_scanned=len(records), age_threshold=300.0)

    assert [event["cycle"] for event in grouped["batman_stale"]] == [3]
    assert [event["cycle"] for event in grouped["batman_age_threshold"]] == [3]
    assert [event["cycle"] for event in grouped["lucius_unapproved"]] == [3]
    assert appended == 3
    assert 'batman.status == "stale": 1' in report
    assert "opp_id=OPP-3" in report
    written = events_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(written) == 3


def test_system_scanner_handles_no_matches_without_writing(tmp_path: Path):
    path = tmp_path / "executions.jsonl"
    events_path = tmp_path / "system_events.jsonl"
    path.write_text(
        json.dumps({"cycle": 1, "decision": "PASS", "batman": {"status": "ok", "age_seconds": 10.0}}),
        encoding="utf-8",
    )

    records = load_system_records(path=path, latest_n=10)
    grouped = collect_system_events(records, age_threshold=300.0)
    appended = append_system_events(events_path, grouped)

    assert appended == 0
    assert not events_path.exists()
