"""Formatting coverage for CYBORG modules."""


def test_dex_opportunity_format():
    from cyborg.core.dex_arbitrage import DexArbitrageScanner

    scanner = DexArbitrageScanner(dry_run=True)
    text = scanner.format_opportunity(
        {
            "token": "ETH",
            "spread_pct": 0.9,
            "cex_price": 3000.0,
            "dex_price": 3027.0,
            "direction": "buy_cex_sell_dex",
            "dex_name": "uniswap",
            "chain": "ethereum",
        }
    )
    assert "ETH" in text
    assert "0.90%" in text


def test_rug_report_format():
    from cyborg.core.rug_detector import RugDetector

    detector = RugDetector(dry_run=True)
    text = detector.format_report(
        {
            "address": "0xabc",
            "chain": "ethereum",
            "honeypot": False,
            "buy_tax_pct": 1.0,
            "sell_tax_pct": 2.0,
            "holder_concentration_pct": 5.0,
            "rug_score": 10,
            "verdict": "low_risk",
        }
    )
    assert "score 10/100" in text


def test_whale_alert_format():
    from cyborg.core.whale_tracker import WhaleTracker

    tracker = WhaleTracker(dry_run=True)
    text = tracker.format_whale_alert(
        {
            "exchange": "Binance",
            "direction": "withdrawal",
            "amount": 125.0,
            "asset": "ETH",
            "chain": "ethereum",
            "signal": "bullish",
        }
    )
    assert "Binance withdrawal" in text


def test_contract_report_format():
    from cyborg.core.contract_scanner import ContractScanner

    scanner = ContractScanner(dry_run=True)
    text = scanner.format_report(
        {
            "address": "0xabc",
            "chain": "ethereum",
            "verified": False,
            "matches": ["selfdestruct"],
            "risk_score": 4,
        }
    )
    assert "risk 4/10" in text
