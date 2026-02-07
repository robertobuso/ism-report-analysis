export type AllocationType = "weight" | "quantity";

export interface User {
  id: string;
  email: string;
  tradestation_user_id: string | null;
  created_at: string;
}

export interface Position {
  id: string;
  symbol: string;
  allocation_type: AllocationType;
  value: number;
}

export interface PositionCreate {
  symbol: string;
  allocation_type: AllocationType;
  value: number;
}

export interface PortfolioVersion {
  id: string;
  version_number: number;
  effective_at: string;
  note: string | null;
  positions: Position[];
  created_at: string;
}

export interface Portfolio {
  id: string;
  name: string;
  base_currency: string;
  created_at: string;
  latest_version: PortfolioVersion | null;
}

export interface PortfolioSummary {
  id: string;
  name: string;
  base_currency: string;
  created_at: string;
  version_count: number;
  position_count: number;
}

export interface PortfolioCreate {
  name: string;
  base_currency: string;
  allocation_type: AllocationType;
  positions: PositionCreate[];
  note?: string;
}

export interface PerformanceSeries {
  portfolio_id: string;
  portfolio_name: string;
  dates: string[];
  nav_values: number[];
  returns: (number | null)[];
}

export interface HoldingContribution {
  symbol: string;
  weight: number;
  return_pct: number;
  contribution: number;
}

export interface Instrument {
  id: string;
  symbol: string;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  logo_url: string | null;
}

export interface PriceDaily {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number;
}

// ============================================================================
// Company Intelligence Types
// ============================================================================

export interface CompanyHeader {
  symbol: string;
  name: string;
  exchange: string;
  sector: string | null;
  industry: string | null;
  current_price: number;
  change_amount: number;
  change_percent: number;
  sparkline: number[];
  shares_held: number | null;
  cost_basis: number | null;
  unrealized_pl: number | null;
  portfolio_weight: number | null;
  contribution_to_return: number | null;
  fetched_at: string;
}

export interface InsightCard {
  type: "market_narrative" | "portfolio_impact" | "earnings_signal";
  severity: "positive" | "neutral" | "negative";
  summary: string;
  tab_target: string;
  data_inputs: Record<string, unknown>;
}

export interface CompanyOverview {
  description: string;
  business_bullets: string[];
  sector: string | null;
  industry: string | null;
  country: string | null;
  market_cap: number | null;
  pe_ratio: number | null;
  forward_pe: number | null;
  eps: number | null;
  dividend_yield: number | null;
  week_52_high: number | null;
  week_52_low: number | null;
  avg_volume: number | null;
  beta: number | null;
  profit_margin: number | null;
  book_value: number | null;
  price_to_book: number | null;
  price_to_sales: number | null;
  shares_outstanding: number | null;
  sec_filings_url: string | null;
  profitability_trend: "improving" | "stable" | "declining" | null;
  leverage_risk: "low" | "moderate" | "high" | null;
  dilution_risk: "low" | "moderate" | "high" | null;
  fetched_at: string;
}

export interface NewsArticle {
  title: string;
  url: string;
  summary: string;
  source: string;
  banner_image: string | null;
  time_published: string;
  overall_sentiment_score: number;
  overall_sentiment_label: string;
  ticker_relevance_score: number;
  ticker_sentiment_score: number;
  ticker_sentiment_label: string;
  topics: string[];
}

export interface SentimentDataPoint {
  date: string;
  score: number;
  article_count: number;
}

export interface NewsSentimentResponse {
  articles: NewsArticle[];
  sentiment_trend: SentimentDataPoint[];
  topic_distribution: Record<string, number>;
  total_articles: number;
  fetched_at: string;
}

export interface EarningsQuarter {
  fiscal_date: string;
  reported_date: string | null;
  reported_eps: number;
  estimated_eps: number;
  surprise: number;
  surprise_pct: number;
}

export interface EarningsResponse {
  quarterly: EarningsQuarter[];
  annual: Record<string, unknown>[];
  beat_rate: number;
  analyst_count: number | null;
  next_earnings_date: string | null;
  fetched_at: string;
}

export interface FinancialStatement {
  fiscal_date: string;
  reported_currency: string;
  data: Record<string, unknown>;
}

export interface FinancialsResponse {
  period: "quarterly" | "annual";
  income_statement: FinancialStatement[];
  balance_sheet: FinancialStatement[];
  cash_flow: FinancialStatement[];
  narrative: string;
  chart_data: Record<string, unknown[]>;
  fetched_at: string;
}

export interface TechnicalIndicatorData {
  indicator: string;
  values: Record<string, unknown>[];
}

export interface SignalSummary {
  trend_vs_50dma: string;
  trend_vs_200dma: string;
  rsi_state: string;
  macd_signal: string;
  volatility_percentile: number;
  interpretation: string;
}

export interface TechnicalsResponse {
  indicators: TechnicalIndicatorData[];
  signal_summary: SignalSummary;
  fetched_at: string;
}

export interface ConcentrationAlert {
  alert_type: string;
  message: string;
  holdings_involved: string[];
  combined_weight: number;
}

export interface HealthScore {
  total: number;
  fundamentals: number;
  price_trend: number;
  sentiment: number;
  portfolio_impact: number;
  breakdown: Record<string, unknown>;
}

export interface PortfolioImpactResponse {
  contribution_to_return: number;
  risk_contribution: number;
  correlation_with_top_holdings: Record<string, number>;
  sector_overlap: Record<string, number>;
  concentration_alerts: ConcentrationAlert[];
  health_score: HealthScore;
  fetched_at: string;
}

export interface ScenarioResult {
  action: string;
  new_weights: Record<string, number>;
  current_volatility: number;
  new_volatility: number;
  current_max_drawdown: number;
  new_max_drawdown: number;
  concentration_change: number;
  risk_ranking_changes: Record<string, unknown>[];
}
