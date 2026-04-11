from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import live_market


def test_fetch_p2p_depth_computes_book_metrics(monkeypatch):
    calls = []

    def fake_request_json(url, **kwargs):
        payload = kwargs["data"]
        calls.append(payload["tradeType"])
        if payload["tradeType"] == "BUY":
            return {
                "data": [
                    {
                        "adv": {
                            "price": "17.20",
                            "dynamicMaxSingleTransAmount": "1000",
                            "minSingleTransAmount": "200",
                        },
                        "advertiser": {"nickName": "desk-a"},
                    },
                    {
                        "adv": {
                            "price": "17.10",
                            "dynamicMaxSingleTransAmount": "500",
                            "minSingleTransAmount": "100",
                        },
                        "advertiser": {"nickName": "desk-b"},
                    },
                ]
            }
        return {
            "data": [
                {
                    "adv": {
                        "price": "17.35",
                        "dynamicMaxSingleTransAmount": "800",
                        "minSingleTransAmount": "200",
                    },
                    "advertiser": {"nickName": "desk-c"},
                },
                {
                    "adv": {
                        "price": "17.40",
                        "dynamicMaxSingleTransAmount": "200",
                        "minSingleTransAmount": "100",
                    },
                    "advertiser": {"nickName": "desk-a"},
                },
            ]
        }

    monkeypatch.setattr(live_market, "_request_json", fake_request_json)

    result = live_market.fetch_p2p_depth(fiat="MXN")

    assert calls == ["BUY", "SELL"]
    assert result["source"] == "binance_p2p_depth"
    assert result["best_buy"] == 17.20
    assert result["best_sell"] == 17.35
    assert round(result["weighted_average"], 4) == 17.2440
    assert result["merchant_count"] == 3
    assert result["liquidity_estimate"] == 2500.0


def test_fetch_p2p_depth_handles_missing_size_values(monkeypatch):
    def fake_request_json(url, **kwargs):
        return {
            "data": [
                {
                    "adv": {"price": "17.20", "dynamicMaxSingleTransAmount": None},
                    "advertiser": {"nickName": "desk-a"},
                }
            ]
        }

    monkeypatch.setattr(live_market, "_request_json", fake_request_json)

    result = live_market.fetch_p2p_depth()

    assert result["best_buy"] == 17.20
    assert result["best_sell"] == 17.20
    assert result["weighted_average"] is None
    assert result["liquidity_estimate"] == 0.0
    assert result["merchant_count"] == 1
