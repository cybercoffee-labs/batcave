"""Tests for CYBORG blockchain intelligence modules."""

import asyncio
from unittest.mock import patch

ETH_SYMBOL = "ETH"


def test_cyborg_package_metadata():
    from cyborg import __codename__, __version__

    assert __codename__ == "CYBORG"
    assert __version__ == "0.1.0"


def test_dex_arbitrage_dry_run():
    from cyborg.core.dex_arbitrage import DexArbitrageScanner

    scanner = DexArbitrageScanner(min_spread_pct=0.5, dry_run=True)
    results = asyncio.run(scanner.scan_all_pairs())

    assert len(results) == 1
    assert results[0]["token"] == ETH_SYMBOL
    assert results[0]["spread_pct"] >= 0.5


def test_dex_arbitrage_scan_filters_small_spreads():
    from cyborg.core.dex_arbitrage import DexArbitrageScanner

    class DummyClient:
        pass

    async def fake_binance(self, client, pair):
        return 100.0 if pair.token == ETH_SYMBOL else 200.0

    async def fake_dex(self, client, pair):
        price = 101.0 if pair.token == ETH_SYMBOL else 200.4
        return {"priceUsd": str(price), "dexId": "uniswap", "chainId": "ethereum", "pairAddress": "0x1"}

    scanner = DexArbitrageScanner(min_spread_pct=0.5)
    with (
        patch.object(DexArbitrageScanner, "_fetch_binance_price", fake_binance),
        patch.object(DexArbitrageScanner, "_fetch_dex_quote", fake_dex),
        patch("cyborg.core.dex_arbitrage.DEFAULT_PAIRS", (scanner_pair("ETH"), scanner_pair("SOL"))),
        patch("cyborg.core.dex_arbitrage.httpx.AsyncClient", DummyAsyncClient),
    ):
        results = asyncio.run(scanner.scan_all_pairs())

    assert len(results) == 1
    assert results[0]["token"] == ETH_SYMBOL


def test_rug_detector_dry_run():
    from cyborg.core.rug_detector import RugDetector

    detector = RugDetector(dry_run=True)
    report = asyncio.run(detector.analyze_token("0xabc", "ethereum"))

    assert report["rug_score"] < 40
    assert report["verdict"] == "low_risk"


def test_rug_detector_handles_api_failure():
    from cyborg.core.rug_detector import RugDetector

    detector = RugDetector()
    with patch.object(RugDetector, "_get_json", return_value=None):
        report = asyncio.run(detector.analyze_token("0xabc", "ethereum"))
    assert report["error"] == "api_unavailable"
    assert report["rug_score"] == 100


def test_whale_tracker_dry_run():
    from cyborg.core.whale_tracker import WhaleTracker

    tracker = WhaleTracker(dry_run=True)
    moves = asyncio.run(tracker.check_recent_whale_moves("ethereum"))

    assert len(moves) == 1
    assert moves[0]["signal"] == "bullish"


def test_whale_tracker_parses_large_moves():
    from cyborg.core.whale_tracker import WhaleTracker

    tracker = WhaleTracker()
    payload = {
        "result": [
            {
                "from": "0xuser",
                "to": KNOWN_WALLET,
                "value": str(150 * 10**18),
                "hash": "0xhash",
            }
        ]
    }
    moves = tracker._parse_native_moves("ethereum", "binance_hot", KNOWN_WALLET, payload)

    assert len(moves) == 1
    assert moves[0]["direction"] == "deposit"
    assert moves[0]["signal"] == "bearish"


def test_contract_scanner_dry_run():
    from cyborg.core.contract_scanner import ContractScanner

    scanner = ContractScanner(dry_run=True)
    report = asyncio.run(scanner.scan_contract("0xabc", "ethereum"))

    assert report["risk_score"] >= 1
    assert "selfdestruct" in report["matches"]


def test_contract_scanner_handles_missing_source():
    from cyborg.core.contract_scanner import ContractScanner

    scanner = ContractScanner()
    with patch.object(
        ContractScanner,
        "_get_json",
        return_value={"result": [{"SourceCode": "", "ABI": "Contract source code not verified"}]},
    ):
        report = asyncio.run(scanner.scan_contract("0xabc", "ethereum"))

    assert report["error"] == "no_source_code"
    assert report["risk_score"] == 10


def test_cyborg_agent_dry_run():
    from cyborg.agent import CyborgAgent

    agent = CyborgAgent(dry_run=True)
    result = asyncio.run(agent.full_scan())

    assert "dex_arbitrage" in result
    assert "whale_moves" in result
    assert len(result["dex_arbitrage"]) == 1


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def scanner_pair(token: str):
    from cyborg.core.dex_arbitrage import ArbitragePair

    return ArbitragePair(token=token, binance_symbol=f"{token}USDT", search_terms=(token,))


KNOWN_WALLET = "0x28c6c06298d514db089934071355e5743bf21d60"
