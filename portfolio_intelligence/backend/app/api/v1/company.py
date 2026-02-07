"""Company Intelligence API endpoints."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_current_user,
    get_alphavantage_client,
    get_llm_service,
    get_redis_cache_service
)
from app.models.user import User
from app.schemas.company import (
    CompanyHeader,
    InsightCard,
    CompanyOverview,
    NewsSentimentResponse,
    EarningsResponse,
    FinancialsResponse,
    TechnicalsResponse,
    PortfolioImpactResponse,
    ScenarioResult
)
from app.services.alphavantage import AlphaVantageClient
from app.services.llm import LLMService
from app.services.redis_cache import RedisCacheService
from app.services.company_intelligence import CompanyIntelligenceService
from app.services.scenario import ScenarioService

router = APIRouter(prefix="/company", tags=["company-intelligence"])


def get_company_intelligence_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    av_client: Annotated[AlphaVantageClient, Depends(get_alphavantage_client)],
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
    cache_service: Annotated[RedisCacheService, Depends(get_redis_cache_service)]
) -> CompanyIntelligenceService:
    """Dependency injection for Company Intelligence service."""
    return CompanyIntelligenceService(
        db=db,
        av_client=av_client,
        llm_service=llm_service,
        cache_service=cache_service
    )


# ============================================================================
# Company Header
# ============================================================================

@router.get("/{symbol}/header", response_model=CompanyHeader)
async def get_company_header(
    symbol: str,
    portfolio_id: uuid.UUID | None = Query(None, description="Portfolio context (optional)"),
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get company header data with optional portfolio context.

    Returns:
    - Company identity (name, sector, industry)
    - Current price + sparkline
    - Portfolio context if portfolio_id provided (shares, weight, contribution)
    """
    try:
        return await service.get_company_header(symbol, portfolio_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching company header: {str(e)}")


# ============================================================================
# Insight Cards (AI-Powered)
# ============================================================================

@router.get("/{symbol}/insights", response_model=list[InsightCard])
async def get_insight_cards(
    symbol: str,
    portfolio_id: uuid.UUID | None = Query(None, description="Portfolio context (optional)"),
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get 3 AI-powered insight cards answering "Why This Matters Now".

    Returns:
    - Market narrative card
    - Portfolio impact card
    - Earnings signal card

    All cards are portfolio-aware if portfolio_id is provided.
    """
    try:
        return await service.get_insight_cards(symbol, portfolio_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating insights: {str(e)}")


# ============================================================================
# Company Overview
# ============================================================================

@router.get("/{symbol}/overview", response_model=CompanyOverview)
async def get_company_overview(
    symbol: str,
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get company overview with fundamentals and quality badges.

    Returns:
    - Business description + AI-generated bullets
    - Key metrics (PE, margins, dividend yield, etc.)
    - Quality badges (profitability trend, leverage risk, dilution risk)
    """
    try:
        return await service.get_company_overview(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching overview: {str(e)}")


# ============================================================================
# News & Sentiment
# ============================================================================

@router.get("/{symbol}/news", response_model=NewsSentimentResponse)
async def get_news_sentiment(
    symbol: str,
    time_range: str | None = Query(None, description="Time range (e.g., '7D', '30D')"),
    sort: str = Query("LATEST", description="Sort order: LATEST, EARLIEST, RELEVANCE"),
    limit: int = Query(50, ge=1, le=200, description="Number of articles (max 200)"),
    sentiment: str | None = Query(None, description="Filter by sentiment"),
    topic: str | None = Query(None, description="Filter by topic"),
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get news articles with sentiment analysis.

    Returns:
    - Articles with sentiment scores and relevance
    - Sentiment trend over time
    - Topic distribution
    """
    try:
        return await service.get_news_sentiment(
            symbol=symbol,
            time_range=time_range,
            sort=sort,
            limit=limit,
            sentiment=sentiment,
            topic=topic
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching news: {str(e)}")


# ============================================================================
# Earnings
# ============================================================================

@router.get("/{symbol}/earnings", response_model=EarningsResponse)
async def get_earnings(
    symbol: str,
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get earnings history with beat rate analysis.

    Returns:
    - Quarterly earnings (actual vs estimate, surprise %)
    - Annual earnings
    - Beat rate (% of quarters that beat estimates)
    """
    try:
        return await service.get_earnings(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching earnings: {str(e)}")


# ============================================================================
# Financials
# ============================================================================

@router.get("/{symbol}/financials", response_model=FinancialsResponse)
async def get_financials(
    symbol: str,
    period: Literal["quarterly", "annual"] = Query("quarterly", description="Financial period"),
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get financial statements with AI narrative.

    Returns:
    - Income statement, balance sheet, cash flow
    - AI-generated narrative explaining trends
    - Pre-computed chart data (revenue, margins, income)
    """
    try:
        return await service.get_financials(symbol, period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching financials: {str(e)}")


# ============================================================================
# Price & Technicals
# ============================================================================

@router.get("/{symbol}/prices")
async def get_prices(
    symbol: str,
    outputsize: str = Query("compact", description="compact (100 days) or full (20+ years)"),
    user: Annotated[User, Depends(get_current_user)] = None,
    av_client: Annotated[AlphaVantageClient, Depends(get_alphavantage_client)] = None
):
    """
    Get daily OHLCV (candlestick) price data.

    Returns:
    - List of daily bars with open, high, low, close, volume
    - Suitable for candlestick chart rendering
    """
    try:
        bars = await av_client.get_daily_bars(symbol, outputsize=outputsize)
        return {"symbol": symbol, "bars": bars, "count": len(bars)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching prices: {str(e)}")


@router.get("/{symbol}/technicals", response_model=TechnicalsResponse)
async def get_technicals(
    symbol: str,
    indicators: str | None = Query(
        None,
        description="Comma-separated indicators (RSI,MACD,BBANDS,SMA)"
    ),
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get technical indicators with AI signal summary.

    Returns:
    - Technical indicator data (RSI, MACD, Bollinger Bands, SMAs)
    - Signal summary (trend, momentum, volatility)
    - AI-generated plain-English interpretation
    """
    try:
        indicator_list = indicators.split(",") if indicators else None
        return await service.get_technicals(symbol, indicator_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching technicals: {str(e)}")


# ============================================================================
# Portfolio Impact
# ============================================================================

@router.get("/{symbol}/portfolio-impact", response_model=PortfolioImpactResponse)
async def get_portfolio_impact(
    symbol: str,
    portfolio_id: uuid.UUID = Query(..., description="Portfolio ID (required)"),
    user: Annotated[User, Depends(get_current_user)] = None,
    service: Annotated[CompanyIntelligenceService, Depends(get_company_intelligence_service)] = None
):
    """
    Get portfolio-aware analysis with concentration alerts and health score.

    Returns:
    - Contribution to portfolio return
    - Risk contribution
    - Sector overlap with other holdings
    - Concentration alerts
    - Position health score (0-100) with 4-component breakdown
    """
    try:
        return await service.get_portfolio_impact(symbol, portfolio_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching portfolio impact: {str(e)}")


# ============================================================================
# Scenario Explorer
# ============================================================================

@router.get("/{symbol}/scenario", response_model=ScenarioResult)
async def run_scenario(
    symbol: str,
    portfolio_id: uuid.UUID = Query(..., description="Portfolio ID (required)"),
    action: Literal["trim_25", "trim_50", "exit", "add_10"] = Query(
        ...,
        description="Action: trim_25 (reduce 25%), trim_50 (reduce 50%), exit (remove), add_10 (increase 10%)"
    ),
    user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None
):
    """
    Run a portfolio scenario simulation.

    Returns:
    - New portfolio weights after action
    - Current vs projected volatility
    - Current vs projected max drawdown
    - Concentration change
    - Risk ranking changes

    Note: This is a simplified v1 using weight-based estimates.
    Full covariance-based modeling will be added in v2.
    """
    try:
        scenario_service = ScenarioService(db)
        return await scenario_service.run_scenario(portfolio_id, symbol, action)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running scenario: {str(e)}")
