"""Whale flow tracker using public Etherscan-compatible APIs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

USER_AGENT = "batman-flow-engine/cyborg/0.1.0"
BASE_DIR = Path(__file__).resolve().parent.parent
CHAIN_CONFIG_FILE = BASE_DIR / "config" / "chains.yaml"

KNOWN_EXCHANGE_WALLETS = {
    "ethereum": {
        "binance_hot": "0x28c6c06298d514db089934071355e5743bf21d60",
        "bybit_hot": "0xf89d7b9c864f589bbf53a82105107622b35eaa40",
    },
    "bsc": {
        "binance_hot": "0x8894e0a0c962cb723c1976a4421c95949be2d4e3",
        "bybit_hot": "0x4a9aa1b39708efb8d95d5e1763a2c51c6df9f4d0",
    },
}

TOKEN_THRESHOLDS = {
    "ETH": 100.0,
    "USDT": 500_000.0,
}

TOKEN_METADATA = {
    "USDT": {
        "ethereum": {
            "contract": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "decimals": 6,
        },
        "bsc": {
            "contract": "0x55d398326f99059ff775485246999027b3197955",
            "decimals": 18,
        },
    }
}


class WhaleTracker:
    """Track large exchange wallet deposits and withdrawals."""

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

    async def check_recent_whale_moves(self, chain: str) -> list[dict[str, Any]]:
        chain_cfg = self.chains.get(chain.lower())
        explorer = chain_cfg.get("explorer") if isinstance(chain_cfg, dict) else None
        wallets = KNOWN_EXCHANGE_WALLETS.get(chain.lower(), {})
        if not explorer or not wallets:
            return []

        if self.dry_run:
            return [
                {
                    "chain": chain,
                    "asset": "ETH",
                    "exchange_wallet": "binance_hot",
                    "exchange": "Binance",
                    "counterparty": "0xdeadbeef",
                    "amount": 125.0,
                    "tx_hash": "dry-run",
                    "direction": "withdrawal",
                    "signal": "bullish",
                }
            ]

        base_url = f"{explorer}/api"
        all_moves: list[dict[str, Any]] = []
        for wallet_name, wallet_address in wallets.items():
            native = await self._fetch_native_moves(base_url, chain.lower(), wallet_name, wallet_address)
            token = await self._fetch_usdt_moves(base_url, chain.lower(), wallet_name, wallet_address)
            all_moves.extend(native)
            all_moves.extend(token)
        return all_moves

    async def _fetch_native_moves(
        self,
        base_url: str,
        chain: str,
        wallet_name: str,
        wallet_address: str,
    ) -> list[dict[str, Any]]:
        payload = await self._get_json(
            base_url,
            {
                "module": "account",
                "action": "txlist",
                "address": wallet_address,
                "sort": "desc",
                "page": 1,
                "offset": 25,
                "apikey": self.etherscan_api_key,
            },
        )
        return self._parse_native_moves(chain, wallet_name, wallet_address, payload)

    async def _fetch_usdt_moves(
        self,
        base_url: str,
        chain: str,
        wallet_name: str,
        wallet_address: str,
    ) -> list[dict[str, Any]]:
        token_meta = TOKEN_METADATA.get("USDT", {}).get(chain)
        if not token_meta:
            return []
        payload = await self._get_json(
            base_url,
            {
                "module": "account",
                "action": "tokentx",
                "address": wallet_address,
                "contractaddress": token_meta["contract"],
                "sort": "desc",
                "page": 1,
                "offset": 25,
                "apikey": self.etherscan_api_key,
            },
        )
        return self._parse_token_moves(chain, wallet_name, wallet_address, payload, token_meta["decimals"])

    def _parse_native_moves(
        self,
        chain: str,
        wallet_name: str,
        wallet_address: str,
        payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        results = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        moves: list[dict[str, Any]] = []
        for tx in results:
            amount = _to_unit(tx.get("value"), 18)
            if amount < TOKEN_THRESHOLDS["ETH"]:
                continue
            direction = _classify_direction(wallet_address, tx.get("from"), tx.get("to"))
            if not direction:
                continue
            moves.append(
                self._build_move(
                    chain=chain,
                    asset="ETH",
                    wallet_name=wallet_name,
                    counterparty=tx.get("from") if direction == "deposit" else tx.get("to"),
                    amount=amount,
                    tx_hash=tx.get("hash", ""),
                    direction=direction,
                )
            )
        return moves

    def _parse_token_moves(
        self,
        chain: str,
        wallet_name: str,
        wallet_address: str,
        payload: dict[str, Any] | None,
        decimals: int,
    ) -> list[dict[str, Any]]:
        results = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        moves: list[dict[str, Any]] = []
        for tx in results:
            amount = _to_unit(tx.get("value"), decimals)
            if amount < TOKEN_THRESHOLDS["USDT"]:
                continue
            direction = _classify_direction(wallet_address, tx.get("from"), tx.get("to"))
            if not direction:
                continue
            moves.append(
                self._build_move(
                    chain=chain,
                    asset="USDT",
                    wallet_name=wallet_name,
                    counterparty=tx.get("from") if direction == "deposit" else tx.get("to"),
                    amount=amount,
                    tx_hash=tx.get("hash", ""),
                    direction=direction,
                )
            )
        return moves

    def _build_move(
        self,
        *,
        chain: str,
        asset: str,
        wallet_name: str,
        counterparty: Any,
        amount: float,
        tx_hash: str,
        direction: str,
    ) -> dict[str, Any]:
        exchange = "Binance" if "binance" in wallet_name else "Bybit"
        signal = "bearish" if direction == "deposit" else "bullish"
        return {
            "chain": chain,
            "asset": asset,
            "exchange_wallet": wallet_name,
            "exchange": exchange,
            "counterparty": str(counterparty or ""),
            "amount": round(amount, 4),
            "tx_hash": tx_hash,
            "direction": direction,
            "signal": signal,
        }

    def format_whale_alert(self, move: dict[str, Any]) -> str:
        return (
            f"[CYBORG][WHALE] {move['exchange']} {move['direction']} "
            f"{move['amount']:,.2f} {move['asset']} on {move['chain']} -> {move['signal']}"
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


def _to_unit(value: Any, decimals: int) -> float:
    try:
        return int(str(value)) / (10**decimals)
    except (TypeError, ValueError):
        return 0.0


def _classify_direction(wallet_address: str, from_address: Any, to_address: Any) -> str | None:
    wallet = wallet_address.lower()
    if str(to_address or "").lower() == wallet:
        return "deposit"
    if str(from_address or "").lower() == wallet:
        return "withdrawal"
    return None
