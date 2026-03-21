"""
Unit tests for core/market_data.py
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.market_data import (
    fetch_simulated_prices,
    fetch_prices,
    SIMULATED_PRICES,
)


def test_fetch_simulated_prices():
    """Test simulated prices returns valid data."""
    result = fetch_simulated_prices()
    assert result["mode"] == "SIMULATED"
    assert "BTCUSDT" in result["prices"]
    assert "ETHUSDT" in result["prices"]
    assert result["prices"]["BTCUSDT"] > 0


def test_fetch_simulated_prices_variation():
    """Test simulated prices have small variation."""
    result = fetch_simulated_prices()
    btc = result["prices"]["BTCUSDT"]
    base = SIMULATED_PRICES["BTCUSDT"]
    assert abs(btc - base) / base < 0.01


def test_fetch_prices_simulated_mode():
    """Test fetch_prices routes to simulated."""
    result = fetch_prices("SIMULATED")
    assert result["mode"] == "SIMULATED"
    assert result["source"] == "seeded_data"


def test_fetch_prices_live_mode():
    """Test LIVE mode returns a live-market or fallback payload."""
    result = fetch_prices("LIVE")
    assert result["mode"] == "LIVE"
    assert result["source"] in {"live_market", "seeded_data_fallback"}


def test_fetch_prices_unknown_mode():
    """Test unknown mode defaults to SIMULATED."""
    result = fetch_prices("UNKNOWN")
    assert result["mode"] == "SIMULATED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
