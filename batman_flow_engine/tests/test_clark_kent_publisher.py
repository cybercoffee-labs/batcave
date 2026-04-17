"""Tests for Binance Square publishing in Clark Kent."""

import json
from unittest.mock import patch

from clark_kent.publisher import BINANCE_SQUARE_URL, ClarkKent


class MockSquareResponse:
    """Minimal urlopen response wrapper for publisher tests."""

    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


@patch.dict("os.environ", {"BINANCE_SQUARE_API_KEY": "test-square-key"}, clear=False)
@patch("urllib.request.urlopen")
def test_post_to_square_uses_verified_endpoint_and_headers(mock_urlopen):
    """Clark Kent should call the verified Binance Square Creator API."""
    mock_urlopen.return_value = MockSquareResponse({"code": "000000", "data": {"id": 12345}})
    publisher = ClarkKent(dry_run=False)

    assert publisher._post_to_square("Test post from Batcave API") is True

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == BINANCE_SQUARE_URL
    assert json.loads(request.data.decode("utf-8")) == {"bodyTextOnly": "Test post from Batcave API"}
    assert request.headers["X-square-openapi-key"] == "test-square-key"
    assert request.headers["Clienttype"] == "binanceSkill"
    assert request.headers["Content-type"] == "application/json"


@patch.dict("os.environ", {"BINANCE_SQUARE_API_KEY": "test-square-key"}, clear=False)
@patch("urllib.request.urlopen")
def test_post_to_square_rejects_non_success_codes(mock_urlopen):
    """HTTP 200 alone is not enough; Binance code must indicate success."""
    mock_urlopen.return_value = MockSquareResponse({"code": "220011", "message": "Content cannot be empty"})
    publisher = ClarkKent(dry_run=False)

    assert publisher._post_to_square("Test post from Batcave API") is False


@patch.dict("os.environ", {}, clear=True)
def test_post_to_square_requires_api_key():
    """Publisher should refuse live posting without the Square API key."""
    publisher = ClarkKent(dry_run=False)

    assert publisher._post_to_square("Test post from Batcave API") is False


def test_publish_resolves_template_key_to_real_post_text(tmp_path):
    """P2P scanners should render the template body, not the template key."""
    publisher = ClarkKent(dry_run=True)
    publisher.storage_file = tmp_path / "published.jsonl"
    publisher.analytics_file = tmp_path / "analytics.jsonl"
    publisher.scheduler.storage_file = publisher.storage_file
    publisher.calendar.storage_file = publisher.storage_file
    publisher.scheduler.can_post_now = lambda: True
    publisher.scheduler.can_post_today = lambda: True
    publisher.calendar.validate_post = lambda text: True

    published = publisher.publish(
        {
            "opp_id": "OPP-F-TEST",
            "scanner_id": "F-P2P-CROSS-CURRENCY",
            "type": "F",
            "asset": "USDT",
            "market": "MXN/ARS",
            "buy_fiat": "MXN",
            "sell_fiat": "ARS",
            "edge_net": 4.8,
            "route": "MXN→USDT(Binance P2P)→USDT→ARS(Binance P2P)",
        }
    )

    assert published is True
    last_line = publisher.storage_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["post"] != "p2p"
    assert "P2P Alert" in payload["post"]
