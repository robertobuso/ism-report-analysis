"""AlphaVantage client for market data."""
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class AlphaVantageClient:
    """Client for AlphaVantage market data API."""

    def __init__(self, api_key: str | None = None):
        self._settings = get_settings()
        self.api_key = api_key or self._settings.alphavantage_api_key
        self._client = httpx.AsyncClient(timeout=30.0)
        self.base_url = "https://www.alphavantage.co/query"

    async def get_daily_bars(
        self,
        symbol: str,
        outputsize: str = "compact",  # "compact" = 100 days, "full" = 20+ years
    ) -> list[dict[str, Any]]:
        """
        Fetch daily OHLCV bars for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            outputsize: "compact" (100 days) or "full" (20+ years)

        Returns:
            List of bars with: date, open, high, low, close, adjusted_close, volume
        """
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol}: {data['Error Message']}")
                return []

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return []

            if "Time Series (Daily)" not in data:
                logger.error(f"Unexpected response for {symbol}: {data}")
                return []

            # Parse time series
            time_series = data["Time Series (Daily)"]
            bars = []

            for date_str, values in time_series.items():
                bars.append({
                    "TimeStamp": f"{date_str}T00:00:00Z",
                    "Open": float(values["1. open"]),
                    "High": float(values["2. high"]),
                    "Low": float(values["3. low"]),
                    "Close": float(values["4. close"]),
                    "AdjustedClose": float(values["5. adjusted close"]),
                    "Volume": int(values["6. volume"]),
                })

            # Sort by date (oldest first)
            bars.sort(key=lambda x: x["TimeStamp"])

            logger.info(f"Fetched {len(bars)} bars for {symbol} from AlphaVantage")
            return bars

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching {symbol} from AlphaVantage: {e}")
            return []

    async def get_quote(self, symbol: str) -> dict[str, Any] | None:
        """
        Get real-time quote for a symbol.

        Returns:
            Quote data with: symbol, price, change, change_percent, volume
        """
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Global Quote" not in data or not data["Global Quote"]:
                logger.warning(f"No quote data for {symbol}")
                return None

            quote = data["Global Quote"]
            return {
                "symbol": quote["01. symbol"],
                "price": float(quote["05. price"]),
                "change": float(quote["09. change"]),
                "change_percent": quote["10. change percent"].rstrip("%"),
                "volume": int(quote["06. volume"]),
                "latest_trading_day": quote["07. latest trading day"],
            }

        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return None

    async def get_intraday_bars(
        self,
        symbol: str,
        interval: str = "5min",  # 1min, 5min, 15min, 30min, 60min
        outputsize: str = "compact",
    ) -> list[dict[str, Any]]:
        """
        Fetch intraday bars (for day trading analytics).

        Args:
            symbol: Stock symbol
            interval: Bar interval (1min, 5min, 15min, 30min, 60min)
            outputsize: "compact" (latest 100) or "full" (trailing 30 days)

        Returns:
            List of intraday bars
        """
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            time_series_key = f"Time Series ({interval})"
            if time_series_key not in data:
                logger.error(f"No intraday data for {symbol}")
                return []

            time_series = data[time_series_key]
            bars = []

            for timestamp, values in time_series.items():
                bars.append({
                    "TimeStamp": timestamp,
                    "Open": float(values["1. open"]),
                    "High": float(values["2. high"]),
                    "Low": float(values["3. low"]),
                    "Close": float(values["4. close"]),
                    "Volume": int(values["5. volume"]),
                })

            bars.sort(key=lambda x: x["TimeStamp"])
            return bars

        except Exception as e:
            logger.error(f"Error fetching intraday for {symbol}: {e}")
            return []

    @staticmethod
    def parse_bars(bars: list[dict]) -> list[dict]:
        """
        Parse AlphaVantage bar response into normalized format.
        Compatible with TradeStation parse_bars format.
        """
        parsed = []
        for bar in bars:
            try:
                parsed.append({
                    "date": datetime.fromisoformat(bar["TimeStamp"].replace("Z", "+00:00")).date(),
                    "open": Decimal(str(bar["Open"])),
                    "high": Decimal(str(bar["High"])),
                    "low": Decimal(str(bar["Low"])),
                    "close": Decimal(str(bar["Close"])),
                    "adj_close": Decimal(str(bar.get("AdjustedClose", bar["Close"]))),
                    "volume": int(bar.get("Volume", 0)),
                })
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping bar due to parse error: {e}")
                continue
        return parsed

    async def close(self):
        await self._client.aclose()


# For backward compatibility with TradeStation interface
class AlphaVantageAdapter:
    """
    Adapter to make AlphaVantage compatible with TradeStation interface.

    This allows swapping AlphaVantage for TradeStation with minimal code changes.
    """

    def __init__(self, api_key: str | None = None):
        self.av_client = AlphaVantageClient(api_key)

    async def get_daily_bars(
        self,
        access_token: str,  # Ignored for AlphaVantage
        symbol: str,
        bars_back: int = 30,
        unit: str = "Daily",  # Ignored for AlphaVantage (always daily)
    ) -> list[dict[str, Any]]:
        """
        Get daily bars - compatible with TradeStation interface.

        Note: access_token is ignored (AlphaVantage uses API key).
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔵 AlphaVantageAdapter: Fetching {bars_back} bars for {symbol}")

        # AlphaVantage "compact" = 100 days, "full" = 20+ years
        outputsize = "full" if bars_back > 100 else "compact"

        bars = await self.av_client.get_daily_bars(symbol, outputsize)

        # Limit to requested bars_back
        if bars_back and len(bars) > bars_back:
            bars = bars[-bars_back:]

        return bars

    @staticmethod
    def parse_bars(bars: list[dict]) -> list[dict]:
        """Parse bars - compatible with TradeStation interface."""
        return AlphaVantageClient.parse_bars(bars)

    async def close(self):
        await self.av_client.close()
