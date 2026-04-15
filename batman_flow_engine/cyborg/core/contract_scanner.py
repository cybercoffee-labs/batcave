"""Static heuristic contract scanner using Etherscan source code."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx
import yaml

USER_AGENT = "batman-flow-engine/cyborg/0.1.0"
BASE_DIR = Path(__file__).resolve().parent.parent
CHAIN_CONFIG_FILE = BASE_DIR / "config" / "chains.yaml"

PATTERNS: dict[str, tuple[re.Pattern[str], int]] = {
    "reentrancy": (re.compile(r"\.call\s*\{value:|call\.value\(", re.IGNORECASE), 3),
    "honeypot": (re.compile(r"blacklist|anti(bot|sell)|trading(enabled|open)", re.IGNORECASE), 2),
    "unlimited_mint": (re.compile(r"\bfunction\s+mint\b|\b_mint\s*\(", re.IGNORECASE), 2),
    "selfdestruct": (re.compile(r"\bselfdestruct\b", re.IGNORECASE), 2),
    "high_trading_fee": (re.compile(r"\b([1-9][0-9]|[1-9][1-9])\s*%\b|taxFee\s*=\s*(1[1-9]|[2-9]\d)", re.IGNORECASE), 1),
    "unlimited_approval": (re.compile(r"type\(uint(256)?\)\.max|2\*\*256\s*-\s*1", re.IGNORECASE), 1),
}


class ContractScanner:
    """Fetch verified source code and score simple exploit patterns."""

    def __init__(self, timeout: float = 10.0, dry_run: bool = False) -> None:
        self.timeout = timeout
        self.dry_run = dry_run
        self.chains = _load_chains()
        _load_dotenv(BASE_DIR.parent / ".env")
        self.etherscan_api_key = os.getenv("ETHERSCAN_API_KEY", "")

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if self.dry_run:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def scan_contract(self, address: str, chain: str) -> dict[str, Any]:
        if self.dry_run:
            dry_source = """
            contract DryRunToken {
                uint256 public taxFee = 15;
                function mint(address to, uint256 amount) external {}
                function doom() external { selfdestruct(payable(msg.sender)); }
            }
            """
            return self._build_report(address, chain, dry_source, verified=True)

        chain_cfg = self.chains.get(chain.lower())
        explorer = chain_cfg.get("explorer") if isinstance(chain_cfg, dict) else None
        if not explorer:
            return {"address": address, "chain": chain, "error": "unsupported_chain", "risk_score": 10}

        payload = await self._get_json(
            f"{explorer}/api",
            {
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
                "apikey": self.etherscan_api_key,
            },
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list) or not result:
            return {"address": address, "chain": chain, "error": "api_unavailable", "risk_score": 10}

        contract_data = result[0]
        source_code = str(contract_data.get("SourceCode", "") or "")
        verified = contract_data.get("ABI") != "Contract source code not verified"
        if not source_code:
            return {
                "address": address,
                "chain": chain,
                "verified": verified,
                "matches": [],
                "risk_score": 10 if not verified else 0,
                "error": "no_source_code",
            }
        return self._build_report(address, chain, source_code, verified=verified)

    def _build_report(self, address: str, chain: str, source_code: str, *, verified: bool) -> dict[str, Any]:
        matches: list[str] = []
        score = 0
        for name, (pattern, weight) in PATTERNS.items():
            if pattern.search(source_code):
                matches.append(name)
                score += weight
        if not verified:
            score = min(score + 2, 10)
        return {
            "address": address,
            "chain": chain,
            "verified": verified,
            "matches": matches,
            "risk_score": min(score, 10),
        }

    def format_report(self, report: dict[str, Any]) -> str:
        if "error" in report and report["error"] != "no_source_code":
            return f"[CYBORG][CONTRACT] {report['chain']} {report['address']} unavailable: {report['error']}"
        matches = ", ".join(report.get("matches", [])) or "no exploit patterns"
        return (
            f"[CYBORG][CONTRACT] {report['chain']} {report['address']} | "
            f"risk {report['risk_score']}/10 | verified={report.get('verified', False)} | {matches}"
        )


def _load_chains() -> dict[str, Any]:
    try:
        return yaml.safe_load(CHAIN_CONFIG_FILE.read_text()) or {}
    except Exception:
        return {}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    except Exception:
        return
