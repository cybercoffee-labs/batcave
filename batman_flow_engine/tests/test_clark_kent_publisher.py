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
