import json
import pathlib
from core.database import save_metrics


def compute_risk_score(data: dict) -> dict:
    equities = data.get("equities", {})
    scores = {}
    for sym, v in equities.items():
        if not v.get("status", "").startswith("ok"):
            continue
        vol_z = v.get("vol_z") or 0
        rvol = v.get("rvol") or 0
        ret1d = v.get("ret_1d") or 0
        dd = min(ret1d, 0)  # drawdown proxy
        risk_score = round(0.4 * abs(vol_z) + 0.3 * min(rvol, 5) + 0.3 * abs(dd) * 100, 4)
        regime = (
            "EXTREME"
            if risk_score > 3.0
            else "STRESS"
            if risk_score > 2.0
            else "TENSION"
            if risk_score > 1.0
            else "NORMAL"
        )
        scores[sym] = {"vol_z": vol_z, "rvol": rvol, "ret1d": ret1d, "risk_score": risk_score, "regime": regime}
        try:
            save_metrics(sym, scores[sym])
        except Exception:
            pass

    top = sorted(scores.items(), key=lambda x: x[1]["risk_score"], reverse=True)
    print("\n🦇 RISK SCORES TOP 10")
    print(f"{'SYM':<8} {'VOL_Z':>6} {'RISK':>6} {'REGIME':<10}")
    print("-" * 35)
    for sym, s in top[:10]:
        print(f"{sym:<8} {s['vol_z']:>6.2f} {s['risk_score']:>6.2f} {s['regime']:<10}")
    return scores


if __name__ == "__main__":
    data = json.loads(pathlib.Path("storage/latest.json").read_text())
    compute_risk_score(data)
