const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchWithAuth(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem("token");

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/login";
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Auth
  getMe: () => fetchWithAuth("/api/v1/auth/me"),

  // Portfolios
  listPortfolios: () => fetchWithAuth("/api/v1/portfolios"),
  getPortfolio: (id: string) => fetchWithAuth(`/api/v1/portfolios/${id}`),
  createPortfolio: (data: unknown) =>
    fetchWithAuth("/api/v1/portfolios", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deletePortfolio: (id: string) =>
    fetchWithAuth(`/api/v1/portfolios/${id}`, { method: "DELETE" }),
  refreshPrices: (id: string) =>
    fetchWithAuth(`/api/v1/portfolios/${id}/refresh-prices`, {
      method: "POST",
    }),
  createVersion: (portfolioId: string, data: unknown) =>
    fetchWithAuth(`/api/v1/portfolios/${portfolioId}/versions`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listVersions: (portfolioId: string) =>
    fetchWithAuth(`/api/v1/portfolios/${portfolioId}/versions`),

  // Instruments
  searchInstruments: (q: string) =>
    fetchWithAuth(`/api/v1/instruments/search?q=${encodeURIComponent(q)}`),
  getInstrument: (symbol: string) =>
    fetchWithAuth(`/api/v1/instruments/${symbol}`),
  getPrices: (symbol: string, start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return fetchWithAuth(
      `/api/v1/instruments/${symbol}/prices?${params.toString()}`,
    );
  },

  // Analytics
  getPerformance: (portfolioId: string, start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return fetchWithAuth(
      `/api/v1/analytics/portfolios/${portfolioId}/performance?${params.toString()}`,
    );
  },
  comparePortfolios: (ids: string[], start?: string, end?: string) => {
    const params = new URLSearchParams();
    params.set("ids", ids.join(","));
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return fetchWithAuth(
      `/api/v1/analytics/portfolios/compare?${params.toString()}`,
    );
  },
  getLatestMetrics: (portfolioId: string) =>
    fetchWithAuth(`/api/v1/analytics/portfolios/${portfolioId}/metrics/latest`),
  getAttribution: (portfolioId: string, period: string = "90d") =>
    fetchWithAuth(
      `/api/v1/analytics/portfolios/${portfolioId}/attribution?period=${period}`,
    ),
  getHoldings: (portfolioId: string) =>
    fetchWithAuth(`/api/v1/portfolios/${portfolioId}/holdings`),

  // Company Intelligence
  getCompanyHeader: (symbol: string, portfolioId?: string) => {
    const params = new URLSearchParams();
    if (portfolioId) params.set("portfolio_id", portfolioId);
    return fetchWithAuth(
      `/api/v1/company/${symbol}/header?${params.toString()}`,
    );
  },
  getCompanyInsights: (symbol: string, portfolioId?: string) => {
    const params = new URLSearchParams();
    if (portfolioId) params.set("portfolio_id", portfolioId);
    return fetchWithAuth(
      `/api/v1/company/${symbol}/insights?${params.toString()}`,
    );
  },
  getCompanyOverview: (symbol: string) =>
    fetchWithAuth(`/api/v1/company/${symbol}/overview`),
  getCompanyNews: (
    symbol: string,
    options?: {
      time_range?: string;
      sort?: string;
      limit?: number;
      sentiment?: string;
      topic?: string;
    },
  ) => {
    const params = new URLSearchParams();
    if (options?.time_range) params.set("time_range", options.time_range);
    if (options?.sort) params.set("sort", options.sort);
    if (options?.limit) params.set("limit", options.limit.toString());
    if (options?.sentiment) params.set("sentiment", options.sentiment);
    if (options?.topic) params.set("topic", options.topic);
    return fetchWithAuth(
      `/api/v1/company/${symbol}/news?${params.toString()}`,
    );
  },
  getCompanyEarnings: (symbol: string) =>
    fetchWithAuth(`/api/v1/company/${symbol}/earnings`),
  getCompanyFinancials: (symbol: string, period: "quarterly" | "annual" = "quarterly") =>
    fetchWithAuth(`/api/v1/company/${symbol}/financials?period=${period}`),
  getCompanyPrices: (symbol: string, outputsize: "compact" | "full" = "compact") =>
    fetchWithAuth(`/api/v1/company/${symbol}/prices?outputsize=${outputsize}`),
  getCompanyTechnicals: (symbol: string, indicators?: string[]) => {
    const params = new URLSearchParams();
    if (indicators && indicators.length > 0) {
      params.set("indicators", indicators.join(","));
    }
    return fetchWithAuth(
      `/api/v1/company/${symbol}/technicals?${params.toString()}`,
    );
  },
  getCompanyPortfolioImpact: (symbol: string, portfolioId: string) =>
    fetchWithAuth(
      `/api/v1/company/${symbol}/portfolio-impact?portfolio_id=${portfolioId}`,
    ),
  getCompanyScenario: (
    symbol: string,
    portfolioId: string,
    action: "trim_25" | "trim_50" | "exit" | "add_10",
  ) =>
    fetchWithAuth(
      `/api/v1/company/${symbol}/scenario?portfolio_id=${portfolioId}&action=${action}`,
    ),
};
