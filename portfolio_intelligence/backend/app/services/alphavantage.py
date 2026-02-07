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

    async def get_company_overview(self, symbol: str) -> dict[str, Any]:
        """
        Get company overview and fundamental data.

        Returns company information including financials, ratios, and sector data.
        """
        params = {
            "function": "OVERVIEW",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol}: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched company overview for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching company overview for {symbol}: {e}")
            return {}

    async def get_news_sentiment(
        self,
        tickers: str,
        time_from: str | None = None,
        time_to: str | None = None,
        sort: str = "LATEST",
        limit: int = 50
    ) -> dict[str, Any]:
        """
        Get news articles with sentiment analysis.

        Args:
            tickers: Stock symbol(s), comma-separated
            time_from: Start time in YYYYMMDDTHHMM format
            time_to: End time in YYYYMMDDTHHMM format
            sort: "LATEST", "EARLIEST", or "RELEVANCE"
            limit: Number of articles (max 1000)

        Returns:
            News feed with sentiment scores per ticker
        """
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": tickers,
            "sort": sort,
            "limit": str(limit),
            "apikey": self.api_key,
        }

        if time_from:
            params["time_from"] = time_from
        if time_to:
            params["time_to"] = time_to

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for news sentiment: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched {len(data.get('feed', []))} news articles for {tickers}")
            return data

        except Exception as e:
            logger.error(f"Error fetching news sentiment for {tickers}: {e}")
            return {}

    async def get_earnings(self, symbol: str) -> dict[str, Any]:
        """
        Get earnings history (quarterly and annual).

        Returns earnings data with estimates, actuals, and surprises.
        """
        params = {
            "function": "EARNINGS",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol}: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched earnings data for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol}: {e}")
            return {}

    async def get_income_statement(self, symbol: str) -> dict[str, Any]:
        """
        Get income statement (quarterly and annual).

        Returns revenue, expenses, and profitability metrics.
        """
        params = {
            "function": "INCOME_STATEMENT",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol}: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched income statement for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching income statement for {symbol}: {e}")
            return {}

    async def get_balance_sheet(self, symbol: str) -> dict[str, Any]:
        """
        Get balance sheet (quarterly and annual).

        Returns assets, liabilities, and equity data.
        """
        params = {
            "function": "BALANCE_SHEET",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol}: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched balance sheet for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching balance sheet for {symbol}: {e}")
            return {}

    async def get_cash_flow(self, symbol: str) -> dict[str, Any]:
        """
        Get cash flow statement (quarterly and annual).

        Returns operating, investing, and financing cash flows.
        """
        params = {
            "function": "CASH_FLOW",
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol}: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched cash flow statement for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching cash flow for {symbol}: {e}")
            return {}

    async def get_technical_indicator(
        self,
        symbol: str,
        indicator: str,
        interval: str = "daily",
        time_period: int = 14,
        series_type: str = "close"
    ) -> dict[str, Any]:
        """
        Get technical indicator data.

        Args:
            symbol: Stock symbol
            indicator: Indicator name (RSI, MACD, BBANDS, SMA, etc.)
            interval: Time interval (daily, weekly, monthly)
            time_period: Number of periods (e.g., 14 for RSI)
            series_type: Price type (close, open, high, low)

        Returns:
            Technical indicator time series
        """
        params = {
            "function": indicator.upper(),
            "symbol": symbol,
            "interval": interval,
            "time_period": str(time_period),
            "series_type": series_type,
            "apikey": self.api_key,
        }

        try:
            response = await self._client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"AlphaVantage error for {symbol} {indicator}: {data['Error Message']}")
                return {}

            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit: {data['Note']}")
                return {}

            logger.info(f"Fetched {indicator} for {symbol}")
            return data

        except Exception as e:
            logger.error(f"Error fetching {indicator} for {symbol}: {e}")
            return {}

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
