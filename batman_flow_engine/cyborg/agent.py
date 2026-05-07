"""Top-level CYBORG orchestration."""

from __future__ import annotations

import asyncio
from typing import Any

from cyborg.core.contract_scanner import ContractScanner
from cyborg.core.dex_arbitrage import DexArbitrageScanner
from cyborg.core.rug_detector import RugDetector
from cyborg.core.whale_tracker import WhaleTracker


class CyborgAgent:
    """Coordinate CYBORG scanners without runtime integration."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dex_arbitrage = DexArbitrageScanner(dry_run=dry_run)
        self.rug_detector = RugDetector(dry_run=dry_run)
        self.whale_tracker = WhaleTracker(dry_run=dry_run)
        self.contract_scanner = ContractScanner(dry_run=dry_run)

    async def full_scan(self) -> dict[str, list[dict[str, Any]]]:
        dex_results, whale_results = await asyncio.gather(
            self.dex_arbitrage.scan_all_pairs(),
            self.whale_tracker.check_recent_whale_moves("ethereum"),
        )
        return {"dex_arbitrage": dex_results, "whale_moves": whale_results}

    async def scan_contract(self, address: str, chain: str = "ethereum") -> dict[str, Any]:
        return await self.contract_scanner.scan_contract(address, chain)

    async def check_token(self, address: str, chain: str = "ethereum") -> dict[str, Any]:
        return await self.rug_detector.analyze_token(address, chain)


async def main() -> None:
    agent = CyborgAgent(dry_run=True)
    summary = await agent.full_scan()
    print(f"DEX arbitrage opportunities: {len(summary['dex_arbitrage'])}")
    print(f"Whale moves: {len(summary['whale_moves'])}")


if __name__ == "__main__":
    asyncio.run(main())
