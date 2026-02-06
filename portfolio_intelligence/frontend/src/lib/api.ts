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
};
