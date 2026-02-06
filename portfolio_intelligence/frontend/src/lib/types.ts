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
