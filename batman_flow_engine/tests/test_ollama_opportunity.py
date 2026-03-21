"""
Tests for BARBARA opportunity analyzer in ollama_intel.py.

These tests mock HTTP calls to localhost:11434 to test the analyze_opportunity
function without requiring a running Ollama instance.
"""

import json
from unittest.mock import patch, MagicMock

from core.ollama_intel import analyze_opportunity


class TestAnalyzeOpportunity:
    """Tests for analyze_opportunity function."""

    @patch("core.ollama_intel.requests.post")
    def test_successful_analysis(self, mock_post):
        """Test successful opportunity analysis with valid response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps(
                {
                    "risk": 3,
                    "action": "act",
                    "confidence": 0.85,
                    "reasoning": "Low risk edge opportunity with good depth",
                }
            )
        }
        mock_post.return_value = mock_response

        opp = {"type": "D", "edge_net": 0.45, "asset": "BTC/USDT", "venue": "Binance"}
        result = analyze_opportunity(opp)

        assert result["status"] == "ok"
        assert result["risk"] == 3
        assert result["action"] == "act"
        assert result["confidence"] == 0.85
        assert "reasoning" in result
        mock_post.assert_called_once()

    @patch("core.ollama_intel.requests.post")
    def test_connection_error_returns_error_dict(self, mock_post):
        """Test that connection errors return error dict."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        opp = {"type": "E", "funding_rate": 0.02, "asset": "ETH/USDT", "venue": "OKX"}
        result = analyze_opportunity(opp)

        assert "error" in result
        assert "Connection error" in result["error"]
        assert "status" not in result  # No status when error

    @patch("core.ollama_intel.requests.post")
    def test_timeout_returns_error_dict(self, mock_post):
        """Test that timeout errors return error dict."""
        import requests

        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        opp = {"type": "F", "edge_net": 1.2, "asset": "USDT/MXN", "venue": "Binance P2P"}
        result = analyze_opportunity(opp)

        assert "error" in result
        assert "timeout" in result["error"].lower()

    @patch("core.ollama_intel.requests.post")
    def test_invalid_json_response_returns_error(self, mock_post):
        """Test that invalid JSON response returns error dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "This is not valid JSON at all"}
        mock_post.return_value = mock_response

        opp = {"type": "G", "merchant_spread_pct": 0.8, "asset": "USDT/ARS", "venue": "Binance P2P"}
        result = analyze_opportunity(opp)

        assert "error" in result
        assert "JSON parse error" in result["error"]

    @patch("core.ollama_intel.requests.post")
    def test_missing_fields_in_response_returns_error(self, mock_post):
        """Test that response missing required fields returns error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps(
                {
                    "risk": 5,
                    "action": "wait",
                    # Missing confidence and reasoning
                }
            )
        }
        mock_post.return_value = mock_response

        opp = {"type": "H", "deviation_pct": 0.3, "asset": "USDC/USDT", "venue": "Binance"}
        result = analyze_opportunity(opp)

        assert "error" in result
        assert "Missing required fields" in result["error"]

    @patch("core.ollama_intel.requests.post")
    def test_invalid_risk_value_normalized(self, mock_post):
        """Test that invalid risk values are normalized to 5."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps(
                {
                    "risk": 15,  # Invalid - should be 1-10
                    "action": "skip",
                    "confidence": 0.7,
                    "reasoning": "Out of range risk",
                }
            )
        }
        mock_post.return_value = mock_response

        opp = {"type": "A", "spread_pct": 0.1, "asset": "BTC/USDT", "venue": "Binance"}
        result = analyze_opportunity(opp)

        assert result["status"] == "ok"
        assert result["risk"] == 5  # Normalized to default

    @patch("core.ollama_intel.requests.post")
    def test_invalid_action_normalized(self, mock_post):
        """Test that invalid action values are normalized to 'wait'."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps(
                {
                    "risk": 4,
                    "action": "BUY_NOW",  # Invalid - should be act/wait/skip
                    "confidence": 0.6,
                    "reasoning": "Invalid action test",
                }
            )
        }
        mock_post.return_value = mock_response

        opp = {"type": "B", "basis_pct": 0.05, "asset": "ETH/USDT", "venue": "OKX"}
        result = analyze_opportunity(opp)

        assert result["status"] == "ok"
        assert result["action"] == "wait"  # Normalized to default

    @patch("core.ollama_intel.requests.post")
    def test_opportunity_field_extraction(self, mock_post):
        """Test that opportunity fields are correctly extracted for different types."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps({"risk": 2, "action": "act", "confidence": 0.9, "reasoning": "Good opportunity"})
        }
        mock_post.return_value = mock_response

        # Test P2P opportunity with market field instead of asset
        opp = {"type": "C", "p2p_premium": 0.8, "market": "MXN", "exchange_buy": "Binance"}
        result = analyze_opportunity(opp)

        assert result["status"] == "ok"
        # Verify the post was called (indicating field extraction worked)
        mock_post.assert_called()
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert "MXN" in payload["prompt"]  # market extracted as asset
