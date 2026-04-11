import json
from pathlib import Path


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def build_alerts(prev: dict | None, curr: dict, flow_threshold: float = 3.0):
    alerts = {"ts": curr.get("timestamp"), "flow_threshold": flow_threshold, "events": []}

    # Engine errors
    if curr.get("meta", {}).get("errors", 0) > 0:
        alerts["events"].append(
            {"type": "ENGINE_ERRORS", "count": curr["meta"]["errors"], "errors": curr.get("errors", [])[:10]}
        )
    # Flow hot (REAL FLOW gate)
    flows = curr.get("flows", {})
    eq = curr.get("equities", {})

    real = []
    for sym, score in flows.items():
        # solo equities: existen en curr["equities"]
        m = eq.get(sym)
        if not isinstance(m, dict):
            continue
        vol_z = float(m.get("vol_z", 0) or 0)
        rvol = float(m.get("rvol", 0) or 0)
        dv = float(m.get("dollar_vol", 0) or 0)

        if (score >= flow_threshold) and (vol_z >= 2.5) and (rvol >= 2.0) and (dv > 0):
            real.append((sym, score, vol_z, rvol, dv))

    real.sort(key=lambda x: x[1], reverse=True)
    if real:
        alerts["events"].append(
            {
                "type": "REAL_FLOW_HOT",
                "count": len(real),
                "top": [
                    {"symbol": s, "flow_score": sc, "vol_z": vz, "rvol": rv, "dollar_vol": dv}
                    for (s, sc, vz, rv, dv) in real[:15]
                ],
            }
        )

    # Narrative shift (simple)
    if prev:
        prev_hits = prev.get("narrative", {}).get("total_hits")
        curr_hits = curr.get("narrative", {}).get("total_hits")
        if isinstance(prev_hits, int) and isinstance(curr_hits, int):
            delta = curr_hits - prev_hits
            if abs(delta) >= 300:
                alerts["events"].append(
                    {"type": "NARRATIVE_SHIFT", "prev_hits": prev_hits, "curr_hits": curr_hits, "delta": delta}
                )

    return alerts


def write_alerts(storage_dir: Path, flow_threshold: float = 3.0):
    storage_dir.mkdir(parents=True, exist_ok=True)
    latest = storage_dir / "latest.json"
    prev = storage_dir / "prev.json"
    alerts_path = storage_dir / "alerts.json"

    curr = load_json(latest)
    prev_data = load_json(prev) if prev.exists() else None
    if not curr:
        return

    alerts = build_alerts(prev_data, curr, flow_threshold=flow_threshold)
    alerts_path.write_text(json.dumps(alerts, indent=2))

    # rotate: latest -> prev
    prev.write_text(json.dumps(curr, indent=2))
