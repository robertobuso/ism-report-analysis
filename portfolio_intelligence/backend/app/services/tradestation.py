import time
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class TradeStationClient:
    """Async client for TradeStation API."""

    def __init__(self):
        self._settings = get_settings()
        self._client = httpx.AsyncClient(timeout=30.0)
        # In-memory access token cache: {user_id: (token, expiry_timestamp)}
        self._token_cache: dict[str, tuple[str, float]] = {}

    def build_auth_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._settings.tradestation_client_id,
            "redirect_uri": self._settings.tradestation_redirect_uri,
            "audience": self._settings.tradestation_audience,
            "scope": "MarketData ReadAccount offline_access openid profile",
            "state": state,
        }
        return f"{self._settings.tradestation_auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access + refresh tokens."""
        response = await self._client.post(
            self._settings.tradestation_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._settings.tradestation_client_id,
                "client_secret": self._settings.tradestation_client_secret,
                "redirect_uri": self._settings.tradestation_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an access token using a refresh token."""
        response = await self._client.post(
            self._settings.tradestation_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._settings.tradestation_client_id,
                "client_secret": self._settings.tradestation_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()

    def cache_access_token(self, user_id: str, token: str, expires_in: int = 1200) -> None:
        """Cache access token with expiry (default 20min)."""
        self._token_cache[user_id] = (token, time.time() + expires_in - 60)

    def get_cached_token(self, user_id: str) -> str | None:
        """Get cached access token if still valid."""
        if user_id in self._token_cache:
            token, expiry = self._token_cache[user_id]
            if time.time() < expiry:
                return token
            del self._token_cache[user_id]
        return None

    async def get_user_profile(self, access_token: str) -> dict[str, Any]:
        """Fetch user profile from TradeStation."""
        response = await self._client.get(
            f"{self._settings.tradestation_base_url}/brokerage/accounts",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()

    async def get_daily_bars(
        self,
        access_token: str,
        symbol: str,
        bars_back: int = 30,
        unit: str = "Daily",
    ) -> list[dict[str, Any]]:
        """Fetch daily OHLCV bars for a symbol."""
        response = await self._client.get(
            f"{self._settings.tradestation_base_url}/marketdata/barcharts/{symbol}",
            params={
                "interval": "1",
                "unit": unit,
                "barsback": str(bars_back),
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("Bars", [])

    @staticmethod
    def parse_bars(bars: list[dict]) -> list[dict]:
        """Parse TradeStation bar response into normalized format."""
        parsed = []
        for bar in bars:
            try:
                parsed.append({
                    "date": datetime.fromisoformat(bar["TimeStamp"].replace("Z", "+00:00")).date(),
                    "open": Decimal(str(bar["Open"])),
                    "high": Decimal(str(bar["High"])),
                    "low": Decimal(str(bar["Low"])),
                    "close": Decimal(str(bar["Close"])),
                    "adj_close": Decimal(str(bar["Close"])),  # TradeStation provides adjusted by default
                    "volume": int(bar.get("TotalVolume", 0)),
                })
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping bar due to parse error: {e}")
                continue
        return parsed

    async def close(self):
        await self._client.aclose()


tradestation_client = TradeStationClient()
