"""
BATCAVE Economic Flow Observatory.

Central read-only telemetry layer for BATCAVE. The observatory inspects
existing storage artifacts, runtime snapshots, and local module presence
without modifying the canonical engine path or any database state.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.economic_graph import build_graph
from core.economic_graph import _load_signal_records_from_db
from core.gordon import get_system_health


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = STORAGE_DIR / "logs"
REPORTS_DIR = STORAGE_DIR / "reports"
DB_PATH = STORAGE_DIR / "batman.db"

OPPORTUNITY_LOGS = (
    LOGS_DIR / "opportunities_old.jsonl",
    LOGS_DIR / "opportunities.jsonl",
)
LATEST_SNAPSHOT_PATH = STORAGE_DIR / "latest.json"
NIGHTWING_CANDIDATE_PATHS = (
    BASE_DIR / "storage" / "logs" / "executions.jsonl",
    BASE_DIR / "storage" / "logs" / "agent.log",
)

STALE_SIGNAL_THRESHOLD_MINUTES = 90


@dataclass(frozen=True)
class PersonaSpec:
    key: str
    title: str
    layer: str
    responsibility: str
    status: str
    module_paths: tuple[str, ...] = ()
    notes: str = ""


PERSONA_SPECS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        key="batman",
        title="BATMAN",
        layer="Intelligence Core",
        responsibility="Canonical runtime, scanners, signal production, persistence.",
        status="implemented",
        module_paths=("engine.py",),
        notes="Protected canonical runtime entrypoint via engine.run_engine().",
    ),
    PersonaSpec(
        key="batcomputer",
        title="BATCOMPUTER",
        layer="Detection Fabric",
        responsibility="Cross-exchange, basis/funding, and P2P detection fabric.",
        status="implemented",
        module_paths=(
            "core/scanner_cross_exchange.py",
            "core/scanner_basis.py",
            "core/p2p_latam.py",
        ),
        notes="Implemented as scanner modules instead of a single facade.",
    ),
    PersonaSpec(
        key="alfred",
        title="ALFRED",
        layer="Data Quality Layer",
        responsibility="Freshness and payload quality checks with dq_score reporting.",
        status="implemented",
        module_paths=("core/alfred.py",),
    ),
    PersonaSpec(
        key="barbara",
        title="BARBARA",
        layer="Narrative Intelligence",
        responsibility="Narrative/context generation and cycle summaries.",
        status="partial",
        module_paths=("core/ollama_intel.py", "core/news_intel.py"),
        notes="Local Ollama and narrative paths exist; broader macro causality remains planned.",
    ),
    PersonaSpec(
        key="harvey",
        title="HARVEY",
        layer="Memory / Ledger / Analytics",
        responsibility="SQLite persistence and analytics over opportunity records.",
        status="implemented",
        module_paths=("core/harvey.py",),
    ),
    PersonaSpec(
        key="lucius",
        title="LUCIUS",
        layer="Compliance / Policy Engine",
        responsibility="Jurisdiction, exposure semantics, and policy helpers.",
        status="partial",
        module_paths=("core/lucius.py",),
        notes="Present in repo but not core-gated inside the canonical runtime.",
    ),
    PersonaSpec(
        key="gordon",
        title="GORDON",
        layer="Safety / Security / Incident Control",
        responsibility="Kill switch, runtime guard, audit trail, and health inspection.",
        status="partial",
        module_paths=("core/gordon.py", "core/gordon_integration.py"),
        notes="Standalone scaffolding exists; reviewed runtime insertion remains pending.",
    ),
    PersonaSpec(
        key="commander",
        title="COMMANDER",
        layer="Control Plane / Orchestration",
        responsibility="Scheduler, supervision, and subsystem coordination.",
        status="partial",
        module_paths=("runner.py", "tools/run_loop.py"),
        notes="Basic orchestration exists, but explicit control-plane maturity is incomplete.",
    ),
    PersonaSpec(
        key="vicki",
        title="VICKI",
        layer="Reporting / Visualization",
        responsibility="Dashboards, local reporting, snapshots, and graph views.",
        status="partial",
        module_paths=("app.py", "graph_engine.py", "live_graph.py", "p2p_flow_dashboard.py"),
        notes="Visualization surfaces exist without a dedicated VICKI module boundary yet.",
    ),
    PersonaSpec(
        key="nightwing",
        title="NIGHTWING",
        layer="Primary Operator",
        responsibility="External operator consuming Batman outputs.",
        status="external",
        module_paths=("operators/nightwing_operator.py",),
        notes="Separate runtime not present in this repo; local adapter is scaffold-only.",
    ),
    PersonaSpec(
        key="red_hood",
        title="RED HOOD",
        layer="Future Spot Operator",
        responsibility="Future specialized spot operator.",
        status="scaffold",
        module_paths=("operators/red_hood.py",),
    ),
    PersonaSpec(
        key="red_robin",
        title="RED ROBIN",
        layer="Future Basis / Futures Operator",
        responsibility="Future basis and futures operator.",
        status="scaffold",
        module_paths=("operators/red_robin.py",),
    ),
    PersonaSpec(
        key="robin",
        title="ROBIN",
        layer="Future Macro Operator",
        responsibility="Future macro, ETF, bonds, and regime operator.",
        status="scaffold",
        module_paths=("operators/robin.py",),
    ),
)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _iter_opportunity_records(
    *,
    db_path: Path = DB_PATH,
    opportunity_logs: tuple[Path, ...] = OPPORTUNITY_LOGS,
) -> list[dict[str, Any]]:
    db_records = _load_signal_records_from_db(db_path)
    if db_records:
        db_records.sort(
            key=lambda item: _parse_timestamp(item.get("ts") or item.get("timestamp"))
            or datetime.min.replace(tzinfo=UTC)
        )
        return db_records

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for path in opportunity_logs:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    opp_id = str(record.get("opp_id") or "")
                    if opp_id and opp_id in seen_ids:
                        continue
                    if opp_id:
                        seen_ids.add(opp_id)
                    records.append(record)
        except OSError:
            continue

    records.sort(key=lambda item: _parse_timestamp(item.get("ts")) or datetime.min.replace(tzinfo=UTC))
    return records


def _derive_market(record: dict[str, Any]) -> str:
    market = record.get("market")
    if isinstance(market, str) and market.strip():
        return market.strip().upper()
    venue = record.get("venue")
    if isinstance(venue, str) and venue.strip():
        return venue.strip()
    return "UNKNOWN"


def _derive_edge_net(record: dict[str, Any]) -> float | None:
    for field in ("edge_net", "basis_pct", "spread_pct", "p2p_premium", "edge"):
        value = _safe_float(record.get(field))
        if value is not None:
            return value
    return None


def _derive_viable(record: dict[str, Any], edge_net: float | None) -> bool | None:
    if isinstance(record.get("viable"), bool):
        return bool(record["viable"])
    if edge_net is None:
        return None
    return edge_net > 0


def _derive_depth(record: dict[str, Any]) -> float | None:
    return _safe_float(record.get("depth_estimate"))


def _bucket_counts(
    records: list[dict[str, Any]],
    *,
    bucket: str,
    limit: int,
    scanner_specific: bool = False,
) -> list[dict[str, Any]]:
    counts: dict[str, Counter[str]] | Counter[str]
    counts = defaultdict(Counter) if scanner_specific else Counter()

    for record in records:
        ts = _parse_timestamp(record.get("ts"))
        if ts is None:
            continue
        if bucket == "hour":
            label = ts.strftime("%Y-%m-%d %H:00 UTC")
        else:
            label = ts.strftime("%Y-%m-%d")
        if scanner_specific:
            scanner = str(record.get("scanner_id") or "UNKNOWN")
            counts[label][scanner] += 1
        else:
            counts[label] += 1

    ordered_labels = sorted(counts.keys())[-limit:]
    if scanner_specific:
        return [{"bucket": label, "scanners": dict(sorted(counts[label].items()))} for label in ordered_labels]
    return [{"bucket": label, "count": counts[label]} for label in ordered_labels]


def _signals_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    scanner_rollup: dict[str, dict[str, Any]] = {}
    market_rollup: dict[str, dict[str, Any]] = {}
    viable_count = 0
    viable_denominator = 0
    depth_values: list[float] = []
    edge_values: list[float] = []

    grouped_scanner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_market: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in records:
        scanner = str(record.get("scanner_id") or "UNKNOWN")
        market = _derive_market(record)
        grouped_scanner[scanner].append(record)
        grouped_market[market].append(record)

        edge_net = _derive_edge_net(record)
        depth = _derive_depth(record)
        viable = _derive_viable(record, edge_net)
        if edge_net is not None:
            edge_values.append(edge_net)
        if depth is not None:
            depth_values.append(depth)
        if viable is not None:
            viable_denominator += 1
            viable_count += int(viable)

    for scanner, group in sorted(grouped_scanner.items()):
        edges = [value for value in (_derive_edge_net(record) for record in group) if value is not None]
        depths = [value for value in (_derive_depth(record) for record in group) if value is not None]
        viable_values = [_derive_viable(record, _derive_edge_net(record)) for record in group]
        viable_known = [value for value in viable_values if value is not None]
        scanner_rollup[scanner] = {
            "signals": len(group),
            "average_edge_net": _round(sum(edges) / len(edges), 4) if edges else None,
            "average_depth_estimate": _round(sum(depths) / len(depths), 2) if depths else None,
            "viable_signal_percentage": _round((sum(bool(v) for v in viable_known) / len(viable_known)) * 100, 2)
            if viable_known
            else None,
            "last_seen": max(
                (
                    (_parse_timestamp(record.get("ts")) or datetime.min.replace(tzinfo=UTC)).isoformat()
                    for record in group
                ),
                default=None,
            ),
        }

    for market, group in sorted(grouped_market.items()):
        edges = [value for value in (_derive_edge_net(record) for record in group) if value is not None]
        depths = [value for value in (_derive_depth(record) for record in group) if value is not None]
        viable_values = [_derive_viable(record, _derive_edge_net(record)) for record in group]
        viable_known = [value for value in viable_values if value is not None]
        market_rollup[market] = {
            "signals": len(group),
            "scanners": sorted({str(record.get("scanner_id") or "UNKNOWN") for record in group}),
            "average_edge_net": _round(sum(edges) / len(edges), 4) if edges else None,
            "average_depth_estimate": _round(sum(depths) / len(depths), 2) if depths else None,
            "viable_signal_percentage": _round((sum(bool(v) for v in viable_known) / len(viable_known)) * 100, 2)
            if viable_known
            else None,
        }

    return {
        "signals_total": len(records),
        "signals_per_scanner": scanner_rollup,
        "signals_per_market": market_rollup,
        "average_edge_net": _round(sum(edge_values) / len(edge_values), 4) if edge_values else None,
        "average_depth_estimate": _round(sum(depth_values) / len(depth_values), 2) if depth_values else None,
        "viable_signal_percentage": _round((viable_count / viable_denominator) * 100, 2)
        if viable_denominator
        else None,
    }


def _temporal_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "signals_per_hour": _bucket_counts(records, bucket="hour", limit=24),
        "signals_per_day": _bucket_counts(records, bucket="day", limit=14),
        "scanner_activity_over_time": _bucket_counts(records, bucket="day", limit=14, scanner_specific=True),
    }


def _latest_engine_run_timestamp(
    *,
    db_path: Path = DB_PATH,
    latest_snapshot_path: Path = LATEST_SNAPSHOT_PATH,
    reports_dir: Path = REPORTS_DIR,
) -> str | None:
    candidates: list[datetime] = []

    latest_snapshot = _read_json(latest_snapshot_path)
    if latest_snapshot:
        ts = _parse_timestamp(latest_snapshot.get("timestamp"))
        if ts is not None:
            candidates.append(ts)

    if db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            row = conn.execute("SELECT ts FROM engine_runs ORDER BY ts DESC LIMIT 1").fetchone()
            conn.close()
            if row and row[0]:
                ts = _parse_timestamp(row[0])
                if ts is not None:
                    candidates.append(ts)
        except sqlite3.Error:
            pass

    if reports_dir.exists():
        for path in sorted(reports_dir.glob("*.json"))[-5:]:
            snapshot = _read_json(path)
            if not snapshot:
                continue
            ts = _parse_timestamp(snapshot.get("timestamp"))
            if ts is not None:
                candidates.append(ts)

    if not candidates:
        return None
    return max(candidates).isoformat()


def _nightwing_last_execution(
    *,
    candidate_paths: tuple[Path, ...] = NIGHTWING_CANDIDATE_PATHS,
    base_dir: Path = BASE_DIR,
) -> dict[str, Any]:
    for path in candidate_paths:
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            last_ts: datetime | None = None
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        ts = _parse_timestamp(payload.get("ts") or payload.get("timestamp"))
                        if ts is not None:
                            last_ts = ts
                if last_ts is not None:
                    return {
                        "available": True,
                        "timestamp": last_ts.isoformat(),
                        "source": str(path.relative_to(base_dir)),
                        "status": "detected",
                    }
            except OSError:
                continue

        return {
            "available": True,
            "timestamp": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            "source": str(path.relative_to(base_dir)),
            "status": "file_activity_only",
        }

    return {
        "available": False,
        "timestamp": None,
        "source": None,
        "status": "unavailable_from_local_storage",
    }


def _dataset_growth(records: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    recent_window_start = now - timedelta(days=1)
    previous_window_start = now - timedelta(days=2)

    recent = 0
    previous = 0
    daily_counts: Counter[str] = Counter()
    for record in records:
        ts = _parse_timestamp(record.get("ts"))
        if ts is None:
            continue
        daily_counts[ts.strftime("%Y-%m-%d")] += 1
        if ts >= recent_window_start:
            recent += 1
        elif previous_window_start <= ts < recent_window_start:
            previous += 1

    delta = recent - previous
    delta_pct = None if previous == 0 else round((delta / previous) * 100, 2)
    recent_days = sorted(daily_counts.keys())[-7:]
    recent_daily_average = None
    if recent_days:
        recent_daily_average = round(sum(daily_counts[day] for day in recent_days) / len(recent_days), 2)

    return {
        "signals_last_24h": recent,
        "signals_previous_24h": previous,
        "delta_signals": delta,
        "delta_percentage": delta_pct,
        "recent_daily_average": recent_daily_average,
        "days_observed": len(daily_counts),
        "total_signals": len(records),
    }


def _system_health(
    records: list[dict[str, Any]],
    *,
    db_path: Path = DB_PATH,
    latest_snapshot_path: Path = LATEST_SNAPSHOT_PATH,
    reports_dir: Path = REPORTS_DIR,
    candidate_paths: tuple[Path, ...] = NIGHTWING_CANDIDATE_PATHS,
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
) -> dict[str, Any]:
    gordon = get_system_health()
    last_signal_dt = None
    if records:
        last_signal_dt = max((_parse_timestamp(record.get("ts")) for record in records), default=None)

    now = now or datetime.now(UTC)
    signal_age_minutes = None
    stale = None
    if last_signal_dt is not None:
        signal_age_minutes = round((now - last_signal_dt).total_seconds() / 60, 2)
        stale = signal_age_minutes > STALE_SIGNAL_THRESHOLD_MINUTES

    return {
        "last_batman_run_timestamp": _latest_engine_run_timestamp(
            db_path=db_path,
            latest_snapshot_path=latest_snapshot_path,
            reports_dir=reports_dir,
        ),
        "last_signal_timestamp": last_signal_dt.isoformat() if last_signal_dt else None,
        "signal_age_minutes": signal_age_minutes,
        "stale_signal_threshold_minutes": STALE_SIGNAL_THRESHOLD_MINUTES,
        "stale_signals": stale,
        "nightwing_last_execution": _nightwing_last_execution(candidate_paths=candidate_paths, base_dir=base_dir),
        "dataset_growth": _dataset_growth(records, now=now),
        "gordon": gordon,
    }


def _module_state(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unreadable"
    if any(marker in text for marker in ("not_implemented", "Placeholder", "scaffold", "NotImplementedError")):
        return "scaffold"
    return "active"


def get_persona_registry(*, base_dir: Path = BASE_DIR) -> list[dict[str, Any]]:
    """Return the persona registry enriched with live module state."""
    registry: list[dict[str, Any]] = []
    for spec in PERSONA_SPECS:
        paths = [base_dir / module_path for module_path in spec.module_paths]
        module_states = {module_path: _module_state(base_dir / module_path) for module_path in spec.module_paths}
        exists_on_disk = all(path.exists() for path in paths) if paths else False
        if not spec.module_paths:
            repo_state = "external"
        elif any(state == "missing" for state in module_states.values()):
            repo_state = "missing"
        elif all(state == "scaffold" for state in module_states.values()):
            repo_state = "scaffold"
        else:
            repo_state = "active"
        registry.append(
            {
                "key": spec.key,
                "title": spec.title,
                "layer": spec.layer,
                "responsibility": spec.responsibility,
                "status": spec.status,
                "module_paths": list(spec.module_paths),
                "module_states": module_states,
                "exists_on_disk": exists_on_disk,
                "repo_state": repo_state,
                "notes": spec.notes,
            }
        )
    return registry


def _architecture_inspection(*, base_dir: Path = BASE_DIR) -> dict[str, Any]:
    registry = get_persona_registry(base_dir=base_dir)
    active = [item["title"] for item in registry if item["repo_state"] == "active"]
    missing = [item["title"] for item in registry if item["repo_state"] == "missing"]
    scaffolds = [item["title"] for item in registry if item["repo_state"] == "scaffold"]
    external = [item["title"] for item in registry if item["status"] == "external"]
    partial = [item["title"] for item in registry if item["status"] == "partial"]

    return {
        "personas": registry,
        "active_personas": active,
        "missing_modules": missing,
        "scaffold_modules": scaffolds,
        "external_personas": external,
        "partial_personas": partial,
        "summary": {
            "total": len(registry),
            "active": len(active),
            "missing": len(missing),
            "scaffold": len(scaffolds),
            "external": len(external),
            "partial": len(partial),
        },
    }


def build_architecture_status(
    *,
    records: list[dict[str, Any]] | None = None,
    db_path: Path = DB_PATH,
    latest_snapshot_path: Path = LATEST_SNAPSHOT_PATH,
    reports_dir: Path = REPORTS_DIR,
    opportunity_logs: tuple[Path, ...] = OPPORTUNITY_LOGS,
    candidate_paths: tuple[Path, ...] = NIGHTWING_CANDIDATE_PATHS,
    base_dir: Path = BASE_DIR,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Return the BATCAVE observatory snapshot.
    """
    records = (
        records
        if records is not None
        else _iter_opportunity_records(db_path=db_path, opportunity_logs=opportunity_logs)
    )
    signals = _signals_summary(records)
    temporal = _temporal_metrics(records)
    system = _system_health(
        records,
        db_path=db_path,
        latest_snapshot_path=latest_snapshot_path,
        reports_dir=reports_dir,
        candidate_paths=candidate_paths,
        base_dir=base_dir,
        now=now,
    )
    architecture = _architecture_inspection(base_dir=base_dir)
    economic_graph = build_graph(records=records, db_path=db_path)
    top_markets_by_flow = economic_graph["centrality"]["liquidity_hubs"][:5]
    central_nodes = economic_graph["centrality"]["central_nodes"][:5]
    graph_summary = economic_graph["summary"]

    market_flow_summary = {
        "top_markets_by_signal_count": sorted(
            (
                {
                    "market": market,
                    "signals": payload["signals"],
                    "average_edge_net": payload["average_edge_net"],
                    "average_depth_estimate": payload["average_depth_estimate"],
                    "viable_signal_percentage": payload["viable_signal_percentage"],
                }
                for market, payload in signals["signals_per_market"].items()
            ),
            key=lambda item: (-item["signals"], item["market"]),
        )[:5],
        "top_scanners_by_signal_count": sorted(
            (
                {"scanner_id": scanner, "signals": payload["signals"]}
                for scanner, payload in signals["signals_per_scanner"].items()
            ),
            key=lambda item: (-item["signals"], item["scanner_id"]),
        )[:5],
        "average_edge_net": signals["average_edge_net"],
        "average_depth_estimate": signals["average_depth_estimate"],
        "viable_signal_percentage": signals["viable_signal_percentage"],
        "top_markets_by_flow": top_markets_by_flow,
        "central_nodes": central_nodes,
    }

    summary = {
        "signals_total": signals["signals_total"],
        "scanners_total": len(signals["signals_per_scanner"]),
        "markets_total": len(signals["signals_per_market"]),
        "viable_signal_percentage": signals["viable_signal_percentage"],
        "stale_signals": system["stale_signals"],
        "kill_switch_active": system["gordon"]["kill_switch_active"],
        "active_personas": architecture["summary"]["active"],
        "scaffold_modules": architecture["summary"]["scaffold"],
        "missing_modules": architecture["summary"]["missing"],
        "graph_edges": graph_summary["edges_total"],
        "graph_nodes": graph_summary["nodes_total"],
    }

    return {
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "summary": summary,
        "market_flow_summary": market_flow_summary,
        "harvey": signals,
        "temporal": temporal,
        "system_health": system,
        "architecture": architecture,
        "economic_graph": {
            "graph_summary": graph_summary,
            "top_markets_by_flow": top_markets_by_flow,
            "central_nodes": central_nodes,
            "edge_weight_ranking": graph_summary["top_edges_by_flow"],
        },
        "graph_summary": graph_summary,
        "top_markets_by_flow": top_markets_by_flow,
        "central_nodes": central_nodes,
    }


__all__ = [
    "build_architecture_status",
    "get_persona_registry",
]
