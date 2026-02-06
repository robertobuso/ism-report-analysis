"""Mock TradeStation client for testing without real API credentials."""
import time
import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from app.config import get_settings

logger = logging.getLogger(__name__)


# Mock market data for common stocks (30 days of realistic OHLCV data)
MOCK_PRICE_DATA = {
    "AAPL": {
        "base_price": 185.50,
        "volatility": 0.015,
        "trend": 0.001,
    },
    "MSFT": {
        "base_price": 420.30,
        "volatility": 0.012,
        "trend": 0.0008,
    },
    "GOOGL": {
        "base_price": 145.20,
        "volatility": 0.018,
        "trend": 0.0005,
    },
    "AMZN": {
        "base_price": 178.90,
        "volatility": 0.020,
        "trend": 0.0012,
    },
    "TSLA": {
        "base_price": 245.60,
        "volatility": 0.035,
        "trend": -0.0005,
    },
    "NVDA": {
        "base_price": 875.40,
        "volatility": 0.025,
        "trend": 0.0015,
    },
    "META": {
        "base_price": 485.20,
        "volatility": 0.022,
        "trend": 0.0010,
    },
    "SPY": {
        "base_price": 510.75,
        "volatility": 0.008,
        "trend": 0.0004,
    },
    "QQQ": {
        "base_price": 445.30,
        "volatility": 0.010,
        "trend": 0.0006,
    },
    "VTI": {
        "base_price": 265.80,
        "volatility": 0.007,
        "trend": 0.0003,
    },
    "NWL": {
        "base_price": 8.50,
        "volatility": 0.020,
        "trend": -0.0002,
    },
    "STLA": {
        "base_price": 14.25,
        "volatility": 0.025,
        "trend": 0.0001,
    },
}


class MockTradeStationClient:
    """
    Mock implementation of TradeStationClient for testing.

    Provides realistic mock data for:
    - OAuth flow (auth URL, token exchange)
    - User profile
    - Market data (OHLCV bars)

    Matches the interface of TradeStationClient exactly for easy swapping.
    """

    def __init__(self):
        self._settings = get_settings()
        # Simulate in-memory token cache
        self._token_cache: dict[str, tuple[str, float]] = {}
        logger.info("MockTradeStationClient initialized (using mock data)")

    def build_auth_url(self, state: str) -> str:
        """Build mock OAuth URL (points to mock endpoint for testing)."""
        params = {
            "response_type": "code",
            "client_id": "mock_client_id",
            "redirect_uri": self._settings.tradestation_redirect_uri,
            "audience": "https://api.tradestation.com",
            "scope": "MarketData ReadAccount offline_access openid profile",
            "state": state,
        }
        # In production, you could set up a mock OAuth endpoint for testing
        return f"http://localhost:8000/mock/auth?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Mock token exchange - returns fake tokens."""
        logger.info(f"Mock: Exchanging code {code[:10]}... for tokens")
        return {
            "access_token": f"mock_access_token_{int(time.time())}",
            "refresh_token": f"mock_refresh_token_{int(time.time())}",
            "expires_in": 1200,
            "token_type": "Bearer",
        }

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Mock token refresh - returns new fake tokens."""
        logger.info("Mock: Refreshing access token")
        return {
            "access_token": f"mock_access_token_refreshed_{int(time.time())}",
            "refresh_token": refresh_token,  # Refresh token stays same
            "expires_in": 1200,
            "token_type": "Bearer",
        }

    def cache_access_token(self, user_id: str, token: str, expires_in: int = 1200) -> None:
        """Cache access token (same as real client)."""
        self._token_cache[user_id] = (token, time.time() + expires_in - 60)

    def get_cached_token(self, user_id: str) -> str | None:
        """Get cached token (same as real client)."""
        if user_id in self._token_cache:
            token, expiry = self._token_cache[user_id]
            if time.time() < expiry:
                return token
            del self._token_cache[user_id]
        return None

    async def get_user_profile(self, access_token: str) -> dict[str, Any]:
        """Mock user profile - returns fake account data."""
        logger.info("Mock: Fetching user profile")
        return {
            "Accounts": [
                {
                    "AccountID": "MOCK123456",
                    "Alias": "Mock Trading Account",
                    "AccountType": "Margin",
                    "Status": "Active",
                }
            ]
        }

    async def get_daily_bars(
        self,
        access_token: str,
        symbol: str,
        bars_back: int = 30,
        unit: str = "Daily",
    ) -> list[dict[str, Any]]:
        """
        Mock daily bars - generates realistic OHLCV data.

        Uses predefined base prices and volatility to generate realistic
        price movements over the requested period.
        """
        symbol = symbol.upper()
        logger.info(f"Mock: Fetching {bars_back} daily bars for {symbol}")

        # Get base data or use defaults
        price_config = MOCK_PRICE_DATA.get(symbol, {
            "base_price": 100.0,
            "volatility": 0.015,
            "trend": 0.0,
        })

        bars = []
        current_price = price_config["base_price"]
        end_date = datetime.now()

        for i in range(bars_back - 1, -1, -1):
            bar_date = end_date - timedelta(days=i)

            # Skip weekends
            if bar_date.weekday() >= 5:
                continue

            # Generate realistic price movement
            import random
            random.seed(f"{symbol}{bar_date.date()}")  # Deterministic but realistic

            daily_return = random.gauss(price_config["trend"], price_config["volatility"])
            current_price *= (1 + daily_return)

            # Generate OHLC
            daily_volatility = abs(random.gauss(0, price_config["volatility"] * 0.5))
            high = current_price * (1 + daily_volatility)
            low = current_price * (1 - daily_volatility)
            open_price = random.uniform(low, high)
            close_price = current_price

            # Generate volume (realistic range)
            base_volume = 50_000_000 if symbol in ["AAPL", "MSFT", "TSLA"] else 10_000_000
            volume = int(base_volume * random.uniform(0.7, 1.3))

            bars.append({
                "TimeStamp": bar_date.isoformat() + "Z",
                "Open": round(open_price, 2),
                "High": round(high, 2),
                "Low": round(low, 2),
                "Close": round(close_price, 2),
                "TotalVolume": volume,
            })

        return bars

    @staticmethod
    def parse_bars(bars: list[dict]) -> list[dict]:
        """Parse bar response - same logic as real client."""
        parsed = []
        for bar in bars:
            try:
                parsed.append({
                    "date": datetime.fromisoformat(bar["TimeStamp"].replace("Z", "+00:00")).date(),
                    "open": Decimal(str(bar["Open"])),
                    "high": Decimal(str(bar["High"])),
                    "low": Decimal(str(bar["Low"])),
                    "close": Decimal(str(bar["Close"])),
                    "adj_close": Decimal(str(bar["Close"])),
                    "volume": int(bar.get("TotalVolume", 0)),
                })
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping bar due to parse error: {e}")
                continue
        return parsed

    async def close(self):
        """Close client (no-op for mock)."""
        logger.info("Mock: Closing client")
