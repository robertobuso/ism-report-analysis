"""Company Intelligence orchestration service."""
import hashlib
import json
import logging
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.portfolio import Portfolio, PortfolioVersion
from app.models.instrument import Instrument
from app.models.price import PriceDaily
from app.schemas.company import (
    CompanyHeader, InsightCard, CompanyOverview,
    NewsArticle, NewsSentimentResponse, SentimentDataPoint,
    EarningsQuarter, EarningsResponse,
    FinancialStatement, FinancialsResponse,
    TechnicalIndicatorData, SignalSummary, TechnicalsResponse,
    ConcentrationAlert, HealthScore, PortfolioImpactResponse
)
from app.services.alphavantage import AlphaVantageClient
from app.services.redis_cache import RedisCacheService
from app.services.llm import LLMService
from app.services.analytics import PortfolioAnalyticsEngine

logger = logging.getLogger(__name__)


class CompanyIntelligenceService:
    """
    Main orchestration service for Company Intelligence.

    Responsibilities:
    - Cache-through reads for all Alpha Vantage data
    - GPT-5.2 calls for insights & narratives
    - Quality badge computation
    - Position health score computation
    - Concentration alert detection
    """

    def __init__(
        self,
        db: AsyncSession,
        av_client: AlphaVantageClient,
        llm_service: LLMService,
        cache_service: RedisCacheService
    ):
        self.db = db
        self.av = av_client
        self.llm = llm_service
        self.cache = cache_service
        self.settings = get_settings()
        self.analytics_engine = PortfolioAnalyticsEngine(db)

    # ========================================================================
    # Header Data
    # ========================================================================

    async def get_company_header(
        self,
        symbol: str,
        portfolio_id: uuid.UUID | None = None
    ) -> CompanyHeader:
        """
        Get company header data with portfolio context.

        Combines:
        - Real-time quote (GLOBAL_QUOTE)
        - Company overview (OVERVIEW)
        - Portfolio holdings (if portfolio_id provided)
        - Price sparkline (last 30 days from DB)
        """
        # Get quote (cached 5 min)
        cache_key = self.cache.make_key("ci", symbol, "quote")
        quote_data = await self.cache.get(cache_key)

        if not quote_data:
            quote_data = await self.av.get_quote(symbol)
            if quote_data:
                await self.cache.set(cache_key, quote_data, self.settings.cache_ttl_quote)

        # Get overview (cached 24h)
        overview_data = await self._get_cached_overview(symbol)

        # Get sparkline (last 30 closing prices from DB)
        sparkline = await self._get_sparkline(symbol, days=30)

        # Get portfolio context if provided
        portfolio_context = {}
        if portfolio_id:
            portfolio_context = await self._get_portfolio_context(portfolio_id, symbol)

        # Build header
        return CompanyHeader(
            symbol=symbol,
            name=overview_data.get("Name", symbol),
            exchange=overview_data.get("Exchange", ""),
            sector=overview_data.get("Sector"),
            industry=overview_data.get("Industry"),
            current_price=float(quote_data.get("price", 0)) if quote_data else 0.0,
            change_amount=float(quote_data.get("change", 0)) if quote_data else 0.0,
            change_percent=float(quote_data.get("change_percent", 0)) if quote_data else 0.0,
            sparkline=sparkline,
            shares_held=portfolio_context.get("shares_held"),
            cost_basis=portfolio_context.get("cost_basis"),
            unrealized_pl=portfolio_context.get("unrealized_pl"),
            portfolio_weight=portfolio_context.get("weight"),
            contribution_to_return=portfolio_context.get("contribution"),
            fetched_at=datetime.utcnow()
        )

    # ========================================================================
    # Insight Cards (AI-Powered)
    # ========================================================================

    async def get_insight_cards(
        self,
        symbol: str,
        portfolio_id: uuid.UUID | None = None
    ) -> list[InsightCard]:
        """
        Generate 3 AI-powered insight cards.

        Uses GPT-5.2 with portfolio context. Cached 30 min.
        """
        # Cache key includes portfolio_id for portfolio-aware insights
        cache_key = self.cache.make_key("ci", symbol, "insights", str(portfolio_id) if portfolio_id else "none")
        cached = await self.cache.get(cache_key)

        if cached and isinstance(cached, list):
            return [InsightCard(**card) for card in cached]

        # Gather data for GPT
        overview = await self._get_cached_overview(symbol)
        news = await self._get_cached_news(symbol, limit=10)
        earnings = await self._get_cached_earnings(symbol)

        company_data = {
            "symbol": symbol,
            "name": overview.get("Name", symbol),
            "sector": overview.get("Sector"),
            "price": overview.get("PERatio"),
            "recent_news_count": len(news.get("feed", [])),
            "recent_earnings": earnings.get("quarterlyEarnings", [])[:4] if earnings else[]
        }

        portfolio_context = None
        if portfolio_id:
            portfolio_context = await self._get_portfolio_context(portfolio_id, symbol)

        # Generate insights via LLM
        cards = await self.llm.generate_insight_cards(company_data, portfolio_context)

        # Cache result
        cards_dict = [card.model_dump() for card in cards]
        await self.cache.set(cache_key, cards_dict, self.settings.cache_ttl_insights)

        return cards

    # ========================================================================
    # Company Overview
    # ========================================================================

    async def get_company_overview(self, symbol: str) -> CompanyOverview:
        """
        Get company overview with AI-generated business bullets.

        Cached 24h.
        """
        overview_data = await self._get_cached_overview(symbol)

        if not overview_data or not overview_data.get("Name"):
            # Return minimal response if no data (ETFs, unsupported symbols, etc.)
            return CompanyOverview(
                description=f"{symbol} data is not available. This may be an ETF, index, or unsupported security type. Company Intelligence is optimized for individual stocks.",
                business_bullets=[
                    "This security does not have company overview data available",
                    "ETFs and indices require different analysis methods",
                    "Consider viewing fundamentals data if available"
                ],
                fetched_at=datetime.utcnow()
            )

        # Generate business bullets via LLM (cached separately)
        bullets_key = self.cache.make_key("ci", symbol, "bullets")
        bullets = await self.cache.get(bullets_key)

        if not bullets:
            bullets = await self.llm.generate_business_bullets(overview_data)
            await self.cache.set(bullets_key, bullets, self.settings.cache_ttl_overview)

        # Compute quality badges
        profitability_trend = self._compute_profitability_trend(overview_data)
        leverage_risk = self._compute_leverage_risk(overview_data)
        dilution_risk = self._compute_dilution_risk(overview_data)

        return CompanyOverview(
            description=overview_data.get("Description", ""),
            business_bullets=bullets,
            sector=overview_data.get("Sector"),
            industry=overview_data.get("Industry"),
            country=overview_data.get("Country"),
            market_cap=self._safe_float(overview_data.get("MarketCapitalization")),
            pe_ratio=self._safe_float(overview_data.get("PERatio")),
            forward_pe=self._safe_float(overview_data.get("ForwardPE")),
            eps=self._safe_float(overview_data.get("EPS")),
            dividend_yield=self._safe_float(overview_data.get("DividendYield")),
            week_52_high=self._safe_float(overview_data.get("52WeekHigh")),
            week_52_low=self._safe_float(overview_data.get("52WeekLow")),
            avg_volume=self._safe_int(overview_data.get("Volume")),
            beta=self._safe_float(overview_data.get("Beta")),
            profit_margin=self._safe_float(overview_data.get("ProfitMargin")),
            book_value=self._safe_float(overview_data.get("BookValue")),
            price_to_book=self._safe_float(overview_data.get("PriceToBookRatio")),
            price_to_sales=self._safe_float(overview_data.get("PriceToSalesRatioTTM")),
            shares_outstanding=self._safe_int(overview_data.get("SharesOutstanding")),
            sec_filings_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=&dateb=&owner=exclude&count=100",
            profitability_trend=profitability_trend,
            leverage_risk=leverage_risk,
            dilution_risk=dilution_risk,
            fetched_at=datetime.utcnow()
        )

    # ========================================================================
    # News & Sentiment
    # ========================================================================

    async def get_news_sentiment(
        self,
        symbol: str,
        time_range: str | None = None,
        sort: str = "LATEST",
        limit: int = 50,
        sentiment: str | None = None,
        topic: str | None = None
    ) -> NewsSentimentResponse:
        """
        Get news articles with sentiment analysis.

        Cached 15 min.
        """
        # Build cache key based on params
        params_hash = hashlib.md5(
            f"{time_range}-{sort}-{limit}-{sentiment}-{topic}".encode()
        ).hexdigest()[:8]
        cache_key = self.cache.make_key("ci", symbol, "news", params_hash)

        cached = await self.cache.get(cache_key)
        if cached:
            return NewsSentimentResponse(**cached)

        # Fetch news from AV
        news_data = await self.av.get_news_sentiment(
            tickers=symbol,
            sort=sort,
            limit=limit
        )

        if not news_data or "feed" not in news_data:
            return NewsSentimentResponse(
                articles=[],
                sentiment_trend=[],
                topic_distribution={},
                total_articles=0,
                fetched_at=datetime.utcnow()
            )

        # Parse articles
        articles = []
        for item in news_data.get("feed", []):
            # Find ticker-specific sentiment
            ticker_sentiment = next(
                (ts for ts in item.get("ticker_sentiment", []) if ts.get("ticker") == symbol),
                {}
            )

            articles.append(NewsArticle(
                title=item.get("title", ""),
                url=item.get("url", ""),
                summary=item.get("summary", ""),
                source=item.get("source", ""),
                banner_image=item.get("banner_image"),
                time_published=datetime.strptime(item["time_published"], "%Y%m%dT%H%M%S"),
                overall_sentiment_score=float(item.get("overall_sentiment_score", 0)),
                overall_sentiment_label=item.get("overall_sentiment_label", "Neutral"),
                ticker_relevance_score=float(ticker_sentiment.get("relevance_score", 0)),
                ticker_sentiment_score=float(ticker_sentiment.get("ticker_sentiment_score", 0)),
                ticker_sentiment_label=ticker_sentiment.get("ticker_sentiment_label", "Neutral"),
                topics=[t.get("topic", "") for t in item.get("topics", [])]
            ))

        # Compute sentiment trend (daily aggregation)
        sentiment_trend = self._compute_sentiment_trend(articles)

        # Topic distribution
        topic_distribution = {}
        for article in articles:
            for topic in article.topics:
                topic_distribution[topic] = topic_distribution.get(topic, 0) + 1

        response = NewsSentimentResponse(
            articles=articles,
            sentiment_trend=sentiment_trend,
            topic_distribution=topic_distribution,
            total_articles=len(articles),
            fetched_at=datetime.utcnow()
        )

        # Cache
        await self.cache.set(cache_key, response.model_dump(), self.settings.cache_ttl_news)

        return response

    # ========================================================================
    # Earnings
    # ========================================================================

    async def get_earnings(self, symbol: str) -> EarningsResponse:
        """
        Get earnings history with beat rate analysis.

        Cached 24h.
        """
        earnings_data = await self._get_cached_earnings(symbol)

        if not earnings_data or "quarterlyEarnings" not in earnings_data:
            return EarningsResponse(
                quarterly=[],
                annual=[],
                beat_rate=0.0,
                analyst_count=None,
                next_earnings_date=None,
                fetched_at=datetime.utcnow()
            )

        # Parse quarterly earnings
        quarterly = []
        beats = 0
        total = 0

        for q in earnings_data.get("quarterlyEarnings", []):
            reported_eps = self._safe_float(q.get("reportedEPS"))
            estimated_eps = self._safe_float(q.get("estimatedEPS"))

            if reported_eps is not None and estimated_eps is not None:
                surprise = reported_eps - estimated_eps
                surprise_pct = (surprise / estimated_eps * 100) if estimated_eps != 0 else 0.0

                if surprise > 0:
                    beats += 1
                total += 1

                quarterly.append(EarningsQuarter(
                    fiscal_date=q.get("fiscalDateEnding", ""),
                    reported_date=q.get("reportedDate"),
                    reported_eps=reported_eps,
                    estimated_eps=estimated_eps,
                    surprise=surprise,
                    surprise_pct=surprise_pct
                ))

        # Beat rate
        beat_rate = (beats / total * 100) if total > 0 else 0.0

        return EarningsResponse(
            quarterly=quarterly,
            annual=earnings_data.get("annualEarnings", []),
            beat_rate=beat_rate,
            analyst_count=None,  # Not available in AV response
            next_earnings_date=None,  # Not available in AV response
            fetched_at=datetime.utcnow()
        )

    # ========================================================================
    # Financials
    # ========================================================================

    async def get_financials(
        self,
        symbol: str,
        period: Literal["quarterly", "annual"] = "quarterly"
    ) -> FinancialsResponse:
        """
        Get financial statements with AI narrative.

        Cached 24h.
        """
        cache_key = self.cache.make_key("ci", symbol, "financials", period)
        cached = await self.cache.get(cache_key)

        if cached:
            return FinancialsResponse(**cached)

        # Fetch all 3 statements
        income_data = await self._get_cached_income_statement(symbol)
        balance_data = await self._get_cached_balance_sheet(symbol)
        cashflow_data = await self._get_cached_cash_flow(symbol)

        # Parse statements
        key_map = {
            "quarterly": "quarterlyReports",
            "annual": "annualReports"
        }
        key = key_map[period]

        income_statements = [
            FinancialStatement(
                fiscal_date=item.get("fiscalDateEnding", ""),
                reported_currency=item.get("reportedCurrency", "USD"),
                data=item
            )
            for item in income_data.get(key, [])
        ]

        balance_statements = [
            FinancialStatement(
                fiscal_date=item.get("fiscalDateEnding", ""),
                reported_currency=item.get("reportedCurrency", "USD"),
                data=item
            )
            for item in balance_data.get(key, [])
        ]

        cashflow_statements = [
            FinancialStatement(
                fiscal_date=item.get("fiscalDateEnding", ""),
                reported_currency=item.get("reportedCurrency", "USD"),
                data=item
            )
            for item in cashflow_data.get(key, [])
        ]

        # Generate AI narrative
        narrative_key = self.cache.make_key("ci", symbol, "narrative", period)
        narrative = await self.cache.get(narrative_key)

        if not narrative:
            financial_summary = {
                "income": income_statements[0].data if income_statements else {},
                "balance": balance_statements[0].data if balance_statements else {},
                "cashflow": cashflow_statements[0].data if cashflow_statements else {}
            }
            narrative = await self.llm.generate_narrative(financial_summary, "financial")
            await self.cache.set(narrative_key, narrative, self.settings.cache_ttl_narrative)

        # Pre-compute chart data
        chart_data = self._compute_financial_charts(
            income_statements,
            balance_statements,
            cashflow_statements
        )

        response = FinancialsResponse(
            period=period,
            income_statement=income_statements,
            balance_sheet=balance_statements,
            cash_flow=cashflow_statements,
            narrative=narrative,
            chart_data=chart_data,
            fetched_at=datetime.utcnow()
        )

        await self.cache.set(cache_key, response.model_dump(), self.settings.cache_ttl_financials)

        return response

    # ========================================================================
    # Technicals
    # ========================================================================

    async def get_technicals(
        self,
        symbol: str,
        indicators: list[str] | None = None
    ) -> TechnicalsResponse:
        """
        Get technical indicators calculated from price data.

        Only makes 1 Alpha Vantage API call (TIME_SERIES_DAILY).
        Calculates RSI, MACD, Bollinger Bands, SMAs from price data.
        Cached 1h.
        """
        cache_key = self.cache.make_key("ci", symbol, "technicals_full")
        cached = await self.cache.get(cache_key)
        if cached:
            return TechnicalsResponse(**cached)

        # Fetch price data (only 1 API call!)
        bars = await self.av.get_daily_bars(symbol, outputsize="compact")

        if not bars or len(bars) < 50:
            # Not enough data for calculations
            return TechnicalsResponse(
                indicators=[],
                signal_summary=SignalSummary(
                    trend_vs_50dma="unknown",
                    trend_vs_200dma="unknown",
                    rsi_state="unknown",
                    macd_signal="unknown",
                    volatility_percentile=50.0,
                    interpretation="Insufficient price data for technical analysis."
                ),
                fetched_at=datetime.utcnow()
            )

        # Calculate all indicators from price data
        indicator_data = []

        # Calculate RSI (14-period)
        rsi_value = self._calculate_rsi(bars, period=14)
        if rsi_value:
            indicator_data.append(TechnicalIndicatorData(
                indicator="RSI",
                values=[{"value": rsi_value, "period": 14}]
            ))

        # Calculate MACD
        macd_data = self._calculate_macd(bars)
        if macd_data:
            indicator_data.append(TechnicalIndicatorData(
                indicator="MACD",
                values=[macd_data]
            ))

        # Calculate SMAs
        sma_50 = self._calculate_sma(bars, period=50)
        sma_200 = self._calculate_sma(bars, period=200)
        if sma_50 and sma_200:
            indicator_data.append(TechnicalIndicatorData(
                indicator="SMA",
                values=[{"SMA_50": sma_50, "SMA_200": sma_200}]
            ))

        # Calculate Bollinger Bands
        bbands = self._calculate_bollinger_bands(bars, period=20)
        if bbands:
            indicator_data.append(TechnicalIndicatorData(
                indicator="BBANDS",
                values=[bbands]
            ))

        # Generate signal summary
        signal_summary = self._generate_signal_summary(bars, rsi_value, macd_data, sma_50, sma_200)

        response = TechnicalsResponse(
            indicators=indicator_data,
            signal_summary=signal_summary,
            fetched_at=datetime.utcnow()
        )

        # Cache for 1 hour
        await self.cache.set(cache_key, response.model_dump(), self.settings.cache_ttl_technicals)

        return response

    def _calculate_rsi(self, bars: list[dict], period: int = 14) -> float | None:
        """Calculate RSI (Relative Strength Index) from price bars."""
        if len(bars) < period + 1:
            return None

        closes = [bar["Close"] for bar in bars[-period - 1:]]
        gains = []
        losses = []

        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            gains.append(max(change, 0))
            losses.append(abs(min(change, 0)))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    def _calculate_macd(self, bars: list[dict]) -> dict | None:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        if len(bars) < 26:
            return None

        closes = [bar["Close"] for bar in bars]

        # Calculate EMAs
        ema_12 = self._calculate_ema(closes, 12)
        ema_26 = self._calculate_ema(closes, 26)

        if not ema_12 or not ema_26:
            return None

        macd_line = ema_12 - ema_26
        # Signal line is 9-period EMA of MACD line
        signal_line = macd_line * 0.95  # Simplified

        return {
            "macd": round(macd_line, 4),
            "signal": round(signal_line, 4),
            "histogram": round(macd_line - signal_line, 4)
        }

    def _calculate_ema(self, data: list[float], period: int) -> float | None:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(data[-period:]) / period  # Start with SMA

        for price in data[-period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_sma(self, bars: list[dict], period: int) -> float | None:
        """Calculate Simple Moving Average."""
        if len(bars) < period:
            return None

        closes = [bar["Close"] for bar in bars[-period:]]
        return round(sum(closes) / period, 2)

    def _calculate_bollinger_bands(self, bars: list[dict], period: int = 20) -> dict | None:
        """Calculate Bollinger Bands (middle, upper, lower)."""
        if len(bars) < period:
            return None

        closes = [bar["Close"] for bar in bars[-period:]]
        sma = sum(closes) / period

        # Calculate standard deviation
        variance = sum((x - sma) ** 2 for x in closes) / period
        std_dev = variance ** 0.5

        upper = sma + (2 * std_dev)
        lower = sma - (2 * std_dev)

        return {
            "middle": round(sma, 2),
            "upper": round(upper, 2),
            "lower": round(lower, 2),
            "bandwidth": round((upper - lower) / sma * 100, 2)
        }

    def _generate_signal_summary(
        self,
        bars: list[dict],
        rsi: float | None,
        macd: dict | None,
        sma_50: float | None,
        sma_200: float | None
    ) -> SignalSummary:
        """Generate technical signal summary from calculated indicators."""
        current_price = bars[-1]["Close"] if bars else 0

        # Determine trends
        trend_50 = "above" if sma_50 and current_price > sma_50 else "below" if sma_50 else "unknown"
        trend_200 = "above" if sma_200 and current_price > sma_200 else "below" if sma_200 else "unknown"

        # RSI state
        rsi_state = "overbought" if rsi and rsi > 70 else "oversold" if rsi and rsi < 30 else "neutral"

        # MACD signal
        macd_signal = "bullish" if macd and macd["macd"] > macd["signal"] else "bearish" if macd else "neutral"

        # Generate interpretation
        interpretation_parts = []

        if trend_50 == "above" and trend_200 == "above":
            interpretation_parts.append("Price is trading above both 50-day and 200-day moving averages, indicating strong bullish momentum.")
        elif trend_50 == "below" and trend_200 == "below":
            interpretation_parts.append("Price is trading below both key moving averages, suggesting bearish pressure.")
        else:
            interpretation_parts.append("Price shows mixed signals relative to moving averages.")

        if rsi:
            if rsi > 70:
                interpretation_parts.append(f"RSI at {rsi:.1f} indicates overbought conditions.")
            elif rsi < 30:
                interpretation_parts.append(f"RSI at {rsi:.1f} indicates oversold conditions.")
            else:
                interpretation_parts.append(f"RSI at {rsi:.1f} shows balanced momentum.")

        if macd:
            if macd["macd"] > macd["signal"]:
                interpretation_parts.append("MACD line above signal line suggests bullish momentum.")
            else:
                interpretation_parts.append("MACD line below signal line suggests bearish momentum.")

        interpretation = " ".join(interpretation_parts)

        return SignalSummary(
            trend_vs_50dma=trend_50,
            trend_vs_200dma=trend_200,
            rsi_state=rsi_state,
            macd_signal=macd_signal,
            volatility_percentile=50.0,  # Simplified
            interpretation=interpretation
        )

    # ========================================================================
    # Portfolio Impact
    # ========================================================================

    async def get_portfolio_impact(
        self,
        symbol: str,
        portfolio_id: uuid.UUID
    ) -> PortfolioImpactResponse:
        """
        Get portfolio-aware analysis with concentration alerts and health score.

        Cached 30 min (portfolio-specific).
        """
        cache_key = self.cache.make_key("ci", symbol, "impact", str(portfolio_id))
        cached = await self.cache.get(cache_key)

        if cached:
            return PortfolioImpactResponse(**cached)

        # Get portfolio context
        context = await self._get_portfolio_context(portfolio_id, symbol)

        if not context:
            # Symbol not in portfolio
            return PortfolioImpactResponse(
                contribution_to_return=0.0,
                risk_contribution=0.0,
                correlation_with_top_holdings={},
                sector_overlap={},
                concentration_alerts=[],
                health_score=HealthScore(
                    total=50.0,
                    fundamentals=12.5,
                    price_trend=12.5,
                    sentiment=12.5,
                    portfolio_impact=12.5,
                    breakdown={}
                ),
                fetched_at=datetime.utcnow()
            )

        # Get attribution data
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        contributions = await self.analytics_engine.get_contribution_by_holding(
            portfolio_id, start_date, end_date
        )

        symbol_contribution = next(
            (c for c in contributions if c.symbol == symbol),
            None
        )

        contribution_to_return = float(symbol_contribution.contribution) if symbol_contribution else 0.0

        # Simplified risk contribution (weight-based proxy)
        risk_contribution = context.get("weight", 0.0)

        # Get top holdings for correlation (simplified - use sector overlap)
        overview = await self._get_cached_overview(symbol)
        sector = overview.get("Sector", "Unknown")

        # Get all holdings in portfolio with positions eagerly loaded
        result = await self.db.execute(
            select(PortfolioVersion)
            .options(selectinload(PortfolioVersion.positions))
            .where(PortfolioVersion.portfolio_id == portfolio_id)
            .order_by(PortfolioVersion.effective_at.desc())
        )
        current_version = result.scalars().first()

        sector_overlap = {}
        if current_version:
            for pos in current_version.positions:
                if pos.symbol != symbol:
                    pos_overview = await self._get_cached_overview(pos.symbol)
                    pos_sector = pos_overview.get("Sector", "Unknown")
                    if pos_sector == sector:
                        sector_overlap[pos.symbol] = float(pos.value)

        # Generate concentration alerts
        concentration_alerts = await self._generate_concentration_alerts(
            portfolio_id, symbol, context.get("weight", 0.0)
        )

        # Compute health score
        health_score = await self._compute_health_score(
            symbol, portfolio_id, context
        )

        response = PortfolioImpactResponse(
            contribution_to_return=contribution_to_return,
            risk_contribution=risk_contribution,
            correlation_with_top_holdings={},  # Simplified v1
            sector_overlap=sector_overlap,
            concentration_alerts=concentration_alerts,
            health_score=health_score,
            fetched_at=datetime.utcnow()
        )

        await self.cache.set(cache_key, response.model_dump(), self.settings.cache_ttl_insights)

        return response

    # ========================================================================
    # Helper Methods - Caching
    # ========================================================================

    async def _get_cached_overview(self, symbol: str) -> dict:
        """Get company overview with caching."""
        cache_key = self.cache.make_key("ci", symbol, "overview")
        data = await self.cache.get(cache_key)

        if not data:
            data = await self.av.get_company_overview(symbol)
            if data:
                await self.cache.set(cache_key, data, self.settings.cache_ttl_overview)

        return data or {}

    async def _get_cached_news(self, symbol: str, limit: int = 50) -> dict:
        """Get news with caching."""
        cache_key = self.cache.make_key("ci", symbol, "news", "default")
        data = await self.cache.get(cache_key)

        if not data:
            data = await self.av.get_news_sentiment(symbol, limit=limit)
            if data:
                await self.cache.set(cache_key, data, self.settings.cache_ttl_news)

        return data or {}

    async def _get_cached_earnings(self, symbol: str) -> dict:
        """Get earnings with caching."""
        cache_key = self.cache.make_key("ci", symbol, "earnings")
        data = await self.cache.get(cache_key)

        if not data:
            data = await self.av.get_earnings(symbol)
            if data:
                await self.cache.set(cache_key, data, self.settings.cache_ttl_earnings)

        return data or {}

    async def _get_cached_income_statement(self, symbol: str) -> dict:
        """Get income statement with caching."""
        cache_key = self.cache.make_key("ci", symbol, "income")
        data = await self.cache.get(cache_key)

        if not data:
            data = await self.av.get_income_statement(symbol)
            if data:
                await self.cache.set(cache_key, data, self.settings.cache_ttl_financials)

        return data or {}

    async def _get_cached_balance_sheet(self, symbol: str) -> dict:
        """Get balance sheet with caching."""
        cache_key = self.cache.make_key("ci", symbol, "balance")
        data = await self.cache.get(cache_key)

        if not data:
            data = await self.av.get_balance_sheet(symbol)
            if data:
                await self.cache.set(cache_key, data, self.settings.cache_ttl_financials)

        return data or {}

    async def _get_cached_cash_flow(self, symbol: str) -> dict:
        """Get cash flow with caching."""
        cache_key = self.cache.make_key("ci", symbol, "cashflow")
        data = await self.cache.get(cache_key)

        if not data:
            data = await self.av.get_cash_flow(symbol)
            if data:
                await self.cache.set(cache_key, data, self.settings.cache_ttl_financials)

        return data or {}

    # ========================================================================
    # Helper Methods - Data Processing
    # ========================================================================

    async def _get_sparkline(self, symbol: str, days: int = 30) -> list[float]:
        """Get price sparkline from database."""
        result = await self.db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = result.scalar_one_or_none()

        if not instrument:
            return []

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        result = await self.db.execute(
            select(PriceDaily.adj_close)
            .where(
                PriceDaily.instrument_id == instrument.id,
                PriceDaily.date >= start_date,
                PriceDaily.date <= end_date
            )
            .order_by(PriceDaily.date)
        )

        prices = [float(row[0]) for row in result.all()]
        return prices

    async def _get_portfolio_context(
        self,
        portfolio_id: uuid.UUID,
        symbol: str
    ) -> dict[str, Any]:
        """Get portfolio context for a symbol."""
        # Get current version with positions eagerly loaded
        result = await self.db.execute(
            select(PortfolioVersion)
            .options(selectinload(PortfolioVersion.positions))
            .where(PortfolioVersion.portfolio_id == portfolio_id)
            .order_by(PortfolioVersion.effective_at.desc())
        )
        version = result.scalars().first()

        if not version:
            return {}

        # Find position
        position = next((p for p in version.positions if p.symbol == symbol), None)

        if not position:
            return {}

        # Get contribution (also provides properly calculated weight)
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        contributions = await self.analytics_engine.get_contribution_by_holding(
            portfolio_id, start_date, end_date
        )

        contribution = next(
            (c for c in contributions if c.symbol == symbol),
            None
        )

        # Use weight from contribution (already normalized and allocation-type aware)
        weight = float(contribution.weight) if contribution else 0.0

        return {
            "shares_held": float(position.value) if contribution else None,
            "weight": weight,  # Already a decimal (0.30 = 30%)
            "contribution": float(contribution.contribution) if contribution else 0.0,
            "cost_basis": None,  # Not tracked in MVP
            "unrealized_pl": None  # Not tracked in MVP
        }

    def _compute_sentiment_trend(
        self,
        articles: list[NewsArticle]
    ) -> list[SentimentDataPoint]:
        """Aggregate sentiment by day."""
        # Group by date
        by_date: dict[str, list[float]] = {}

        for article in articles:
            date_str = article.time_published.strftime("%Y-%m-%d")
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append(article.ticker_sentiment_score)

        # Compute daily averages
        trend = []
        for date_str in sorted(by_date.keys()):
            scores = by_date[date_str]
            trend.append(SentimentDataPoint(
                date=date_str,
                score=sum(scores) / len(scores),
                article_count=len(scores)
            ))

        return trend

    def _compute_financial_charts(
        self,
        income_statements: list[FinancialStatement],
        balance_statements: list[FinancialStatement],
        cashflow_statements: list[FinancialStatement]
    ) -> dict[str, list]:
        """Pre-compute chart data for frontend."""
        if not income_statements:
            return {}

        # Build chart data arrays with {date, value} objects for Recharts
        revenue = []
        net_income = []
        profit_margin = []
        free_cash_flow = []
        roe = []

        # Create lookup dictionaries by fiscal_date for balance sheet and cash flow
        balance_by_date = {stmt.fiscal_date: stmt for stmt in balance_statements}
        cashflow_by_date = {stmt.fiscal_date: stmt for stmt in cashflow_statements}

        for stmt in income_statements:
            date = stmt.fiscal_date
            total_revenue = self._safe_float(stmt.data.get("totalRevenue"))
            total_net_income = self._safe_float(stmt.data.get("netIncome"))

            # Debug logging for first statement
            if stmt == income_statements[0]:
                logger.info(f"Chart data parsing - First statement:")
                logger.info(f"  Date: {date}")
                logger.info(f"  totalRevenue raw: {stmt.data.get('totalRevenue')}")
                logger.info(f"  totalRevenue parsed: {total_revenue}")
                logger.info(f"  netIncome raw: {stmt.data.get('netIncome')}")
                logger.info(f"  netIncome parsed: {total_net_income}")
                logger.info(f"  Available keys: {list(stmt.data.keys())[:15]}")

            # Revenue chart (use 'is not None' to allow zero values)
            if total_revenue is not None:
                revenue.append({"date": date, "value": total_revenue / 1e9})  # Billions

            # Net Income chart (use 'is not None' to allow zero/negative values)
            if total_net_income is not None:
                net_income.append({"date": date, "value": total_net_income / 1e9})  # Billions

            # Profit Margin chart (%)
            if total_revenue is not None and total_net_income is not None and total_revenue != 0:
                margin = (total_net_income / total_revenue) * 100
                profit_margin.append({"date": date, "value": margin})

            # Free Cash Flow (from cash flow statement)
            if date in cashflow_by_date:
                cf_stmt = cashflow_by_date[date]
                operating_cf = self._safe_float(cf_stmt.data.get("operatingCashflow"))
                capex = self._safe_float(cf_stmt.data.get("capitalExpenditures"))
                if operating_cf is not None and capex is not None:
                    fcf = (operating_cf + capex) / 1e9  # Billions (capex is negative)
                    free_cash_flow.append({"date": date, "value": fcf})

            # ROE (%) = Net Income / Shareholder Equity * 100
            if date in balance_by_date and total_net_income is not None:
                balance_stmt = balance_by_date[date]
                equity = self._safe_float(balance_stmt.data.get("totalShareholderEquity"))
                if equity is not None and equity != 0:
                    roe_value = (total_net_income / equity) * 100
                    roe.append({"date": date, "value": roe_value})

        return {
            "revenue": revenue,
            "net_income": net_income,
            "profit_margin": profit_margin,
            "free_cash_flow": free_cash_flow,
            "roe": roe
        }

    async def _get_signal_summary(
        self,
        symbol: str,
        indicators: list[TechnicalIndicatorData]
    ) -> SignalSummary:
        """Generate technical signal summary with AI interpretation."""
        # Simplified v1 - rule-based
        summary = SignalSummary(
            trend_vs_50dma="neutral",
            trend_vs_200dma="neutral",
            rsi_state="neutral",
            macd_signal="neutral",
            volatility_percentile=50.0,
            interpretation="Technical indicators show mixed signals."
        )

        # Generate AI interpretation
        narrative_key = self.cache.make_key("ci", symbol, "signal_narrative")
        interpretation = await self.cache.get(narrative_key)

        if not interpretation:
            indicator_summary = {
                "indicators": [ind.indicator for ind in indicators],
                "symbol": symbol
            }
            interpretation = await self.llm.generate_narrative(indicator_summary, "signal")
            await self.cache.set(narrative_key, interpretation, self.settings.cache_ttl_technicals)

        summary.interpretation = interpretation

        return summary

    async def _generate_concentration_alerts(
        self,
        portfolio_id: uuid.UUID,
        symbol: str,
        weight: float
    ) -> list[ConcentrationAlert]:
        """Generate concentration risk alerts."""
        alerts = []

        # Position size alert
        if weight > 0.20:
            alerts.append(ConcentrationAlert(
                alert_type="position_size",
                message=f"{symbol} represents {weight * 100:.1f}% of your portfolio (>20%)",
                holdings_involved=[symbol],
                combined_weight=weight
            ))

        # Sector overlap alert (simplified)
        overview = await self._get_cached_overview(symbol)
        sector = overview.get("Sector", "Unknown")

        if sector != "Unknown":
            # Find other holdings in same sector with positions eagerly loaded
            result = await self.db.execute(
                select(PortfolioVersion)
                .options(selectinload(PortfolioVersion.positions))
                .where(PortfolioVersion.portfolio_id == portfolio_id)
                .order_by(PortfolioVersion.effective_at.desc())
            )
            version = result.scalars().first()

            if version:
                sector_holdings = [symbol]
                sector_weight = weight

                for pos in version.positions:
                    if pos.symbol != symbol:
                        pos_overview = await self._get_cached_overview(pos.symbol)
                        if pos_overview.get("Sector") == sector:
                            sector_holdings.append(pos.symbol)
                            sector_weight += float(pos.value)

                if sector_weight > 0.30 and len(sector_holdings) > 1:
                    alerts.append(ConcentrationAlert(
                        alert_type="sector_overlap",
                        message=f"{sector} sector represents {sector_weight * 100:.1f}% of portfolio",
                        holdings_involved=sector_holdings,
                        combined_weight=sector_weight
                    ))

        return alerts

    async def _compute_health_score(
        self,
        symbol: str,
        portfolio_id: uuid.UUID,
        context: dict
    ) -> HealthScore:
        """Compute position health score (equal-weighted composite)."""
        # Simplified v1 - each component is 0-25 points

        # Fundamentals (25 points)
        overview = await self._get_cached_overview(symbol)
        fundamentals_score = self._score_fundamentals(overview)

        # Price trend (25 points)
        sparkline = await self._get_sparkline(symbol, days=90)
        price_trend_score = self._score_price_trend(sparkline)

        # Sentiment (25 points)
        news = await self._get_cached_news(symbol, limit=20)
        sentiment_score = self._score_sentiment(news)

        # Portfolio impact (25 points)
        impact_score = self._score_portfolio_impact(context)

        total = fundamentals_score + price_trend_score + sentiment_score + impact_score

        return HealthScore(
            total=total,
            fundamentals=fundamentals_score,
            price_trend=price_trend_score,
            sentiment=sentiment_score,
            portfolio_impact=impact_score,
            breakdown={
                "fundamentals_basis": "PE ratio, profit margin, debt ratios",
                "price_trend_basis": "90-day price momentum",
                "sentiment_basis": "Recent news sentiment average",
                "portfolio_impact_basis": "Contribution to return, weight balance"
            }
        )

    # ========================================================================
    # Helper Methods - Scoring & Quality Badges
    # ========================================================================

    def _score_fundamentals(self, overview: dict) -> float:
        """Score fundamentals (0-25 points)."""
        score = 12.5  # Start neutral

        pe = self._safe_float(overview.get("PERatio"))
        profit_margin = self._safe_float(overview.get("ProfitMargin"))

        if pe and 10 <= pe <= 25:
            score += 5
        if profit_margin and profit_margin > 0.10:
            score += 5

        return min(25.0, max(0.0, score))

    def _score_price_trend(self, sparkline: list[float]) -> float:
        """Score price trend (0-25 points)."""
        if len(sparkline) < 2:
            return 12.5

        # Simple momentum
        first = sparkline[0]
        last = sparkline[-1]
        change = (last - first) / first if first > 0 else 0.0

        if change > 0.10:
            return 20.0
        elif change > 0:
            return 15.0
        elif change > -0.10:
            return 10.0
        else:
            return 5.0

    def _score_sentiment(self, news_data: dict) -> float:
        """Score sentiment (0-25 points)."""
        feed = news_data.get("feed", [])
        if not feed:
            return 12.5

        scores = [
            item.get("overall_sentiment_score", 0)
            for item in feed[:10]
        ]

        avg = sum(scores) / len(scores) if scores else 0

        # Map sentiment score (-1 to 1) to points
        return 12.5 + (avg * 12.5)

    def _score_portfolio_impact(self, context: dict) -> float:
        """Score portfolio impact (0-25 points)."""
        contribution = context.get("contribution", 0.0)
        weight = context.get("weight", 0.0)

        score = 12.5  # Neutral

        # Positive contribution
        if contribution > 0.05:
            score += 7.5
        elif contribution > 0:
            score += 3.5

        # Balanced weight (not too concentrated)
        if 0.05 <= weight <= 0.15:
            score += 5

        return min(25.0, max(0.0, score))

    def _compute_profitability_trend(
        self,
        overview: dict
    ) -> Literal["improving", "stable", "declining"] | None:
        """Compute profitability trend badge."""
        profit_margin = self._safe_float(overview.get("ProfitMargin"))

        if profit_margin is None:
            return None

        if profit_margin > 0.15:
            return "improving"
        elif profit_margin > 0.05:
            return "stable"
        else:
            return "declining"

    def _compute_leverage_risk(
        self,
        overview: dict
    ) -> Literal["low", "moderate", "high"] | None:
        """Compute leverage risk badge."""
        # Simplified - would use debt/equity ratio in full version
        return "moderate"

    def _compute_dilution_risk(
        self,
        overview: dict
    ) -> Literal["low", "moderate", "high"] | None:
        """Compute dilution risk badge."""
        # Simplified - would compare shares outstanding over time
        return "low"

    # ========================================================================
    # Helper Methods - Type Conversion
    # ========================================================================

    def _safe_float(self, value: Any) -> float | None:
        """Safely convert to float."""
        if value is None or value == "None" or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: Any) -> int | None:
        """Safely convert to int."""
        if value is None or value == "None" or value == "":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

