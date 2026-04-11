from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


from core import live_market
from core.market_data import fetch_live_prices, fetch_prices


def test_fetch_binance_spot_prices_parses_expected_symbols(monkeypatch):
    payload = [
        {"symbol": "BTCUSDT", "price": "68000.10"},
        {"symbol": "ETHUSDT", "price": "2000.50"},
        {"symbol": "IGNORE", "price": "1.0"},
    ]

    monkeypatch.setattr(live_market, "_request_json", lambda *args, **kwargs: payload)

    result = live_market.fetch_binance_spot_prices()

    assert result["source"] == "binance_spot"
    assert result["prices"] == {"BTCUSDT": 68000.10, "ETHUSDT": 2000.50}


def test_fetch_binance_p2p_offers_parses_compact_offer_list(monkeypatch):
    payload = {
        "data": [
            {
                "adv": {
                    "price": "17.25",
                    "minSingleTransAmount": "500",
                    "dynamicMaxSingleTransAmount": "2500",
                },
                "advertiser": {"nickName": "desk-a"},
            }
        ]
    }
    monkeypatch.setattr(live_market, "_request_json", lambda *args, **kwargs: payload)

    result = live_market.fetch_binance_p2p_offers("MXN")

    assert result["fiat"] == "MXN"
    assert result["offers"][0]["price"] == 17.25
    assert result["offers"][0]["nick_name"] == "desk-a"


def test_fetch_exchange_rate_returns_requested_quote(monkeypatch):
    monkeypatch.setattr(live_market, "_request_json", lambda *args, **kwargs: {"rates": {"MXN": 17.1}})

    result = live_market.fetch_exchange_rate()

    assert result["quote"] == "MXN"
    assert result["rate"] == 17.1


def test_fetch_live_prices_falls_back_to_simulated(monkeypatch):
    def raise_error(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("core.market_data.fetch_binance_spot_prices", raise_error)

    result = fetch_live_prices()

    assert result["mode"] == "LIVE"
    assert result["source"] == "seeded_data_fallback"
    assert result["fallback_reason"] == "network down"
    assert "BTCUSDT" in result["prices"]


def test_fetch_prices_live_routes_to_live_market(monkeypatch):
    monkeypatch.setattr(
        "core.market_data.fetch_live_prices",
        lambda: {"mode": "LIVE", "prices": {"BTCUSDT": 1.0}, "source": "live_market"},
    )

    result = fetch_prices("LIVE")

    assert result["mode"] == "LIVE"
    assert result["source"] == "live_market"
