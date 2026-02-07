"""Company Intelligence schemas for API responses."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel


# ============================================================================
# Company Header (Sticky Header Data)
# ============================================================================

class CompanyHeader(BaseModel):
    """Company header data for sticky header section."""
    symbol: str
    name: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    current_price: float
    change_amount: float
    change_percent: float
    sparkline: list[float]  # last 30 closing prices
    shares_held: float | None = None  # None if not in portfolio
    cost_basis: float | None = None
    unrealized_pl: float | None = None
    portfolio_weight: float | None = None
    contribution_to_return: float | None = None
    fetched_at: datetime


# ============================================================================
# Insight Cards (LLM-Generated)
# ============================================================================

class InsightCard(BaseModel):
    """AI-generated insight card for 'Why This Matters Now' section."""
    type: Literal["market_narrative", "portfolio_impact", "earnings_signal"]
    severity: Literal["positive", "neutral", "negative"]
    summary: str  # One sentence
    tab_target: str  # Which tab to navigate to when clicked
    data_inputs: dict[str, Any]  # Source data for explainability


class InsightCardsResponse(BaseModel):
    """Response containing 3 insight cards."""
    cards: list[InsightCard]


# ============================================================================
# Company Overview Tab
# ============================================================================

class CompanyOverview(BaseModel):
    """Company overview data with metrics and quality indicators."""
    description: str
    business_bullets: list[str]  # GPT-generated 3-5 bullets
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    avg_volume: int | None = None
    beta: float | None = None
    profit_margin: float | None = None
    book_value: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    shares_outstanding: int | None = None
    sec_filings_url: str | None = None
    profitability_trend: Literal["improving", "stable", "declining"] | None = None
    leverage_risk: Literal["low", "moderate", "high"] | None = None
    dilution_risk: Literal["low", "moderate", "high"] | None = None
    fetched_at: datetime


# ============================================================================
# News & Sentiment Tab
# ============================================================================

class NewsArticle(BaseModel):
    """Individual news article with sentiment data."""
    title: str
    url: str
    summary: str
    source: str
    banner_image: str | None = None
    time_published: datetime
    overall_sentiment_score: float
    overall_sentiment_label: str
    ticker_relevance_score: float
    ticker_sentiment_score: float
    ticker_sentiment_label: str
    topics: list[str]


class SentimentDataPoint(BaseModel):
    """Sentiment trend data point."""
    date: str
    score: float
    article_count: int


class NewsSentimentResponse(BaseModel):
    """News and sentiment analysis response."""
    articles: list[NewsArticle]
    sentiment_trend: list[SentimentDataPoint]
    topic_distribution: dict[str, int]
    total_articles: int
    fetched_at: datetime


# ============================================================================
# Earnings Tab
# ============================================================================

class EarningsQuarter(BaseModel):
    """Quarterly earnings data."""
    fiscal_date: str
    reported_date: str | None = None
    reported_eps: float
    estimated_eps: float
    surprise: float
    surprise_pct: float


class EarningsResponse(BaseModel):
    """Earnings history and analysis."""
    quarterly: list[EarningsQuarter]
    annual: list[dict]
    beat_rate: float  # % of quarters that beat estimates
    analyst_count: int | None = None
    next_earnings_date: str | None = None
    fetched_at: datetime


# ============================================================================
# Financials Tab
# ============================================================================

class FinancialStatement(BaseModel):
    """Financial statement data for a specific period."""
    fiscal_date: str
    reported_currency: str
    data: dict[str, Any]  # Flexible JSON for all line items


class FinancialsResponse(BaseModel):
    """Financial statements with narrative and chart data."""
    period: Literal["quarterly", "annual"]
    income_statement: list[FinancialStatement]
    balance_sheet: list[FinancialStatement]
    cash_flow: list[FinancialStatement]
    narrative: str  # GPT-generated 2-3 sentence summary
    chart_data: dict[str, list]  # Pre-computed for frontend charts
    fetched_at: datetime


# ============================================================================
# Price & Technicals Tab
# ============================================================================

class TechnicalIndicatorData(BaseModel):
    """Technical indicator time series data."""
    indicator: str  # RSI, MACD, BBANDS, SMA
    values: list[dict[str, Any]]


class SignalSummary(BaseModel):
    """Aggregated technical signals with GPT interpretation."""
    trend_vs_50dma: str  # "above", "below", "converging"
    trend_vs_200dma: str
    rsi_state: str  # "oversold", "neutral", "overbought"
    macd_signal: str  # "bullish", "neutral", "bearish"
    volatility_percentile: float  # 0-100
    interpretation: str  # GPT-generated plain-English summary


class TechnicalsResponse(BaseModel):
    """Technical analysis data and signals."""
    indicators: list[TechnicalIndicatorData]
    signal_summary: SignalSummary
    fetched_at: datetime


# ============================================================================
# Portfolio Impact Tab
# ============================================================================

class ConcentrationAlert(BaseModel):
    """Concentration risk alert."""
    alert_type: str  # "sector_overlap", "theme_overlap", "position_size"
    message: str
    holdings_involved: list[str]
    combined_weight: float


class HealthScore(BaseModel):
    """Position health score with breakdown."""
    total: float  # 0-100
    fundamentals: float  # 0-25
    price_trend: float  # 0-25
    sentiment: float  # 0-25
    portfolio_impact: float  # 0-25
    breakdown: dict[str, Any]  # Explainability details


class PortfolioImpactResponse(BaseModel):
    """Portfolio-aware analysis of the holding."""
    contribution_to_return: float
    risk_contribution: float
    correlation_with_top_holdings: dict[str, float]
    sector_overlap: dict[str, float]
    concentration_alerts: list[ConcentrationAlert]
    health_score: HealthScore
    fetched_at: datetime


# ============================================================================
# Scenario Explorer
# ============================================================================

class ScenarioResult(BaseModel):
    """Result of a portfolio scenario simulation."""
    action: str  # "trim_25", "trim_50", "exit", "add_10"
    new_weights: dict[str, float]
    current_volatility: float
    new_volatility: float
    current_max_drawdown: float
    new_max_drawdown: float
    concentration_change: float
    risk_ranking_changes: list[dict]
