"""Token rug-pull heuristics via GoPlus Labs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml

GOPLUS_URL = "https://api.gopluslabs.io/api/v1/token_security"
USER_AGENT = "batman-flow-engine/cyborg/0.1.0"
BASE_DIR = Path(__file__).resolve().parent.parent
CHAIN_CONFIG_FILE = BASE_DIR / "config" / "chains.yaml"


class RugDetector:
    """Analyze token contract risk using public GoPlus token security data."""

    def __init__(self, timeout: float = 10.0, dry_run: bool = False) -> None:
        self.timeout = timeout
        self.dry_run = dry_run
        self.chains = _load_chains()

    async def _get_json(self, url: str) -> dict[str, Any] | None:
        if self.dry_run:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def analyze_token(self, address: str, chain: str) -> dict[str, Any]:
        chain_id = self._resolve_chain_id(chain)
        if not chain_id:
            return {"address": address, "chain": chain, "error": "unsupported_chain", "rug_score": 100}

        if self.dry_run:
            return {
                "address": address,
                "chain": chain,
                "honeypot": False,
                "ownership_renounced": True,
                "liquidity_locked": True,
                "holder_concentration_pct": 12.5,
                "buy_tax_pct": 2.0,
                "sell_tax_pct": 3.0,
                "contract_verified": True,
                "rug_score": 18,
                "verdict": "low_risk",
            }

        url = f"{GOPLUS_URL}/{chain_id}?contract_addresses={address}"
        payload = await self._get_json(url)
        token_info = self._extract_token_info(payload, address)
        if not token_info:
            return {"address": address, "chain": chain, "error": "api_unavailable", "rug_score": 100}

        report = {
            "address": address,
            "chain": chain,
            "honeypot": _as_bool(token_info.get("is_honeypot")),
            "ownership_renounced": _as_bool(token_info.get("owner_change_balance")) or _as_bool(
                token_info.get("owner_renounced")
            ),
            "liquidity_locked": _as_bool(token_info.get("is_locked")) or _as_bool(token_info.get("lp_locked")),
            "holder_concentration_pct": _pct(token_info.get("holder_percent")),
            "buy_tax_pct": _pct(token_info.get("buy_tax")),
            "sell_tax_pct": _pct(token_info.get("sell_tax")),
            "contract_verified": _as_bool(token_info.get("is_open_source")),
        }
        report["rug_score"] = self._calculate_rug_score(report)
        report["verdict"] = _risk_bucket(report["rug_score"])
        return report

    def _resolve_chain_id(self, chain: str) -> str | None:
        cfg = self.chains.get(chain.lower())
        chain_id = cfg.get("chain_id") if isinstance(cfg, dict) else None
        return str(chain_id) if chain_id is not None else None

    def _extract_token_info(self, payload: dict[str, Any] | None, address: str) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        address_lower = address.lower()
        for key, value in result.items():
            if str(key).lower() == address_lower and isinstance(value, dict):
                return value
        return None

    def _calculate_rug_score(self, report: dict[str, Any]) -> int:
        score = 0
        if report["honeypot"]:
            score += 40
        if not report["ownership_renounced"]:
            score += 15
        if not report["liquidity_locked"]:
            score += 15
        if report["holder_concentration_pct"] >= 50:
            score += 15
        elif report["holder_concentration_pct"] >= 25:
            score += 8
        if report["buy_tax_pct"] > 10:
            score += 7
        if report["sell_tax_pct"] > 10:
            score += 8
        if not report["contract_verified"]:
            score += 10
        return min(score, 100)

    def format_report(self, report: dict[str, Any]) -> str:
        if "error" in report:
            return f"[CYBORG][RUG] {report['chain']} {report['address']} unavailable: {report['error']}"
        return (
            f"[CYBORG][RUG] {report['chain']} {report['address']} | score {report['rug_score']}/100 "
            f"({report['verdict']}) | honeypot={report['honeypot']} "
            f"tax={report['buy_tax_pct']:.1f}/{report['sell_tax_pct']:.1f}% "
            f"holders={report['holder_concentration_pct']:.1f}%"
        )


def _load_chains() -> dict[str, Any]:
    try:
        return yaml.safe_load(CHAIN_CONFIG_FILE.read_text()) or {}
    except Exception:
        return {}


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _pct(value: Any) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return 0.0
    return raw * 100 if raw <= 1 else raw


def _risk_bucket(score: int) -> str:
    if score >= 70:
        return "high_risk"
    if score >= 40:
        return "medium_risk"
    return "low_risk"
