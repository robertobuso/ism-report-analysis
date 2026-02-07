"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  LineChart,
  Legend,
} from "recharts";
import { RefreshCw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/providers/auth-provider";
import { Portfolio, PerformanceSeries } from "@/lib/types";

const TIME_RANGES = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "YTD", days: null },
  { label: "1Y", days: 365 },
  { label: "All", days: null },
];

const SPY_BENCHMARK_ID = "4fd582ca-66c5-4c56-92e7-4b2ca623d188";

function getStartDate(range: (typeof TIME_RANGES)[number]): string | undefined {
  if (range.label === "All") return undefined;
  if (range.label === "YTD") {
    return `${new Date().getFullYear()}-01-01`;
  }
  if (range.days) {
    const d = new Date();
    d.setDate(d.getDate() - range.days);
    return d.toISOString().split("T")[0];
  }
  return undefined;
}

function calculateSharpe(returnYtd: number, volatility: number): number {
  const riskFreeRate = 0.045; // 4.5%
  return (returnYtd - riskFreeRate) / volatility;
}

export default function PortfolioOverviewPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [selectedRange, setSelectedRange] = useState(TIME_RANGES[1]); // 3M default
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: portfolio, isLoading: portfolioLoading } = useQuery<Portfolio>({
    queryKey: ["portfolio", id],
    queryFn: () => api.getPortfolio(id),
    enabled: isAuthenticated,
  });

  const { data: performance, isLoading: perfLoading } =
    useQuery<PerformanceSeries>({
      queryKey: ["performance", id, selectedRange.label],
      queryFn: () => api.getPerformance(id, getStartDate(selectedRange)),
      enabled: isAuthenticated,
    });

  const { data: metrics, error: metricsError, isLoading: metricsLoading } = useQuery<any>({
    queryKey: ["metrics", id],
    queryFn: () => api.getLatestMetrics(id),
    enabled: isAuthenticated,
    retry: 1,
  });

  const { data: attribution } = useQuery<any>({
    queryKey: ["attribution", id],
    queryFn: () => api.getAttribution(id, "90d"),
    enabled: isAuthenticated,
  });

  const { data: holdings } = useQuery<any>({
    queryKey: ["holdings", id],
    queryFn: () => api.getHoldings(id),
    enabled: isAuthenticated,
  });

  const { data: comparison } = useQuery<any>({
    queryKey: ["comparison", id, selectedRange.label],
    queryFn: () =>
      api.comparePortfolios([id, SPY_BENCHMARK_ID], getStartDate(selectedRange)),
    enabled: isAuthenticated,
    retry: false, // Don't retry if SPY benchmark doesn't exist
  });

  if (portfolioLoading) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-48" />
          <div className="h-64 bg-gray-200 rounded-card" />
        </div>
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-8">
        <p className="text-muted">Portfolio not found.</p>
      </div>
    );
  }

  const chartData =
    performance?.dates.map((d, i) => ({
      date: d,
      nav: Number(performance.nav_values[i]),
    })) ?? [];

  const latestNav = chartData.length > 0 ? chartData[chartData.length - 1].nav : null;
  const firstNav = chartData.length > 0 ? chartData[0].nav : null;
  const totalReturn =
    latestNav && firstNav ? ((latestNav - firstNav) / firstNav) * 100 : null;

  // Benchmark comparison data
  const comparisonChartData = comparison?.portfolios?.[0]?.dates.map((d: string, i: number) => ({
    date: d,
    portfolio: Number(comparison.portfolios[0].nav_values[i]),
    spy: Number(comparison.portfolios[1]?.nav_values[i] ?? 0),
  })) ?? [];

  const spyReturn = comparison?.portfolios?.[1]
    ? ((Number(comparison.portfolios[1].nav_values.at(-1)) /
        Number(comparison.portfolios[1].nav_values[0])) -
        1) *
      100
    : null;

  const alpha = totalReturn && spyReturn ? totalReturn - spyReturn : null;

  const sharpeRatio = metrics
    ? calculateSharpe(Number(metrics.return_ytd), Number(metrics.volatility_30d))
    : null;


  const handleRefreshPrices = async () => {
    setIsRefreshing(true);
    setRefreshMessage(null);
    try {
      const result = await api.refreshPrices(id);
      setRefreshMessage(`Refreshing ${result.symbols.length} symbols...`);

      // Wait a bit for background task to complete, then refetch
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["performance", id] });
        queryClient.invalidateQueries({ queryKey: ["metrics", id] });
        queryClient.invalidateQueries({ queryKey: ["attribution", id] });
        queryClient.invalidateQueries({ queryKey: ["holdings", id] });
        queryClient.invalidateQueries({ queryKey: ["comparison", id] });
        setRefreshMessage("✓ Data refreshed!");
        setTimeout(() => setRefreshMessage(null), 3000);
      }, 3000);
    } catch (error) {
      setRefreshMessage("Failed to refresh data");
      setTimeout(() => setRefreshMessage(null), 3000);
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleDeletePortfolio = async () => {
    try {
      await api.deletePortfolio(id);
      router.push("/");
    } catch (error) {
      alert("Failed to delete portfolio");
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{portfolio.name}</h1>
          <p className="text-muted text-sm">{portfolio.base_currency}</p>
        </div>
        <div className="flex items-center gap-3">
          {refreshMessage && (
            <span className="text-sm text-accent-green font-medium">
              {refreshMessage}
            </span>
          )}
          <button
            onClick={handleRefreshPrices}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-button text-sm font-medium hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Refresh latest market data from AlphaVantage"
          >
            <RefreshCw
              size={16}
              className={isRefreshing ? "animate-spin" : ""}
            />
            {isRefreshing ? "Refreshing..." : "Refresh Data"}
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-red-300 text-red-600 rounded-button text-sm font-medium hover:bg-red-50 transition-colors"
            title="Delete this portfolio"
          >
            <Trash2 size={16} />
            Delete
          </button>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-card p-6 max-w-md mx-4">
            <h3 className="text-lg font-bold mb-2">Delete Portfolio?</h3>
            <p className="text-muted mb-4">
              Are you sure you want to delete "{portfolio?.name}"? This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 border border-gray-300 rounded-button text-sm font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeletePortfolio}
                className="px-4 py-2 bg-red-600 text-white rounded-button text-sm font-medium hover:bg-red-700"
              >
                Delete Portfolio
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Key Metrics Row */}
      {metricsError && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-card p-4 mb-6">
          <p className="text-sm text-yellow-800">
            ⚠️ Metrics unavailable - try clicking "Refresh Data" to fetch latest prices
          </p>
        </div>
      )}
      {metrics && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-card shadow-card p-4">
            <div className="text-xs text-muted mb-1">Current NAV</div>
            <div className="text-2xl font-bold">
              ${Number(metrics.nav).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className={`text-sm font-semibold ${Number(metrics.return_ytd) >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {Number(metrics.return_ytd) >= 0 ? "+" : ""}
              {(Number(metrics.return_ytd) * 100).toFixed(2)}% YTD
            </div>
          </div>

          <div className="bg-white rounded-card shadow-card p-4">
            <div className="text-xs text-muted mb-1">30-Day Volatility</div>
            <div className="text-2xl font-bold">
              {(Number(metrics.volatility_30d) * 100).toFixed(1)}%
            </div>
            <div className="text-xs text-muted">Annualized from daily returns</div>
          </div>

          <div className="bg-white rounded-card shadow-card p-4">
            <div className="text-xs text-muted mb-1">Max Drawdown</div>
            <div className="text-2xl font-bold text-accent-red">
              {(Number(metrics.max_drawdown) * 100).toFixed(1)}%
            </div>
            <div className="text-xs text-muted">Peak to trough</div>
          </div>

          <div className="bg-white rounded-card shadow-card p-4">
            <div className="text-xs text-muted mb-1">Sharpe Ratio</div>
            <div className="text-2xl font-bold">
              {sharpeRatio ? sharpeRatio.toFixed(2) : "—"}
            </div>
            <div className="text-xs text-muted">
              {sharpeRatio ? "Risk-adjusted (vs 4.5% risk-free)" : ""}
            </div>
          </div>
        </div>
      )}

      {/* Benchmark Comparison */}
      {alpha !== null && (
        <div className="bg-white rounded-card shadow-card p-6 mb-6">
          <h2 className="font-bold text-lg mb-4">vs. S&P 500</h2>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="text-center p-3 bg-gray-50 rounded">
              <div className="text-xs text-muted mb-1">Your Portfolio</div>
              <div className={`text-xl font-bold ${totalReturn && totalReturn >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {totalReturn && totalReturn >= 0 ? "+" : ""}
                {totalReturn?.toFixed(2)}%
              </div>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <div className="text-xs text-muted mb-1">SPY (S&P 500)</div>
              <div className={`text-xl font-bold ${spyReturn && spyReturn >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {spyReturn && spyReturn >= 0 ? "+" : ""}
                {spyReturn?.toFixed(2)}%
              </div>
            </div>
            <div className="text-center p-3 bg-blue-50 rounded">
              <div className="text-xs text-muted mb-1">Alpha</div>
              <div className={`text-xl font-bold ${alpha >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {alpha >= 0 ? "+" : ""}
                {alpha.toFixed(2)}%
              </div>
              <div className="text-xs text-muted">
                {alpha >= 0 ? "Outperforming" : "Underperforming"}
              </div>
            </div>
          </div>
          {comparisonChartData.length > 0 && (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={comparisonChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "#6c757d" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: "#6c757d" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid #e2e8f0",
                      fontSize: "11px",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Line
                    type="monotone"
                    dataKey="portfolio"
                    stroke="#191970"
                    strokeWidth={2}
                    dot={false}
                    name="Your Portfolio"
                  />
                  <Line
                    type="monotone"
                    dataKey="spy"
                    stroke="#94a3b8"
                    strokeWidth={2}
                    dot={false}
                    name="SPY"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Performance Chart */}
      <div className="bg-white rounded-card shadow-card p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="font-bold text-lg">Performance</h2>
            {latestNav !== null && (
              <div className="text-3xl font-bold mt-2">
                ${latestNav.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            )}
            {totalReturn !== null && (
              <div
                className={`text-sm font-semibold ${totalReturn >= 0 ? "text-accent-green" : "text-accent-red"}`}
              >
                {totalReturn >= 0 ? "+" : ""}
                {totalReturn.toFixed(2)}%
              </div>
            )}
          </div>

          {/* Time Range Selector */}
          <div className="flex gap-1 bg-gray-100 rounded-button p-1">
            {TIME_RANGES.map((range) => (
              <button
                key={range.label}
                onClick={() => setSelectedRange(range)}
                className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                  selectedRange.label === range.label
                    ? "bg-white text-primary shadow-sm"
                    : "text-muted hover:text-foreground"
                }`}
              >
                {range.label}
              </button>
            ))}
          </div>
        </div>

        {/* Chart */}
        <div className="h-64">
          {perfLoading ? (
            <div className="h-full bg-gray-100 rounded animate-pulse" />
          ) : chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="navGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#191970" stopOpacity={0.1} />
                    <stop offset="95%" stopColor="#191970" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: "#6c757d" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#6c757d" }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #e2e8f0",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="nav"
                  stroke="#191970"
                  strokeWidth={2}
                  fill="url(#navGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-muted text-sm">
              No performance data available yet
            </div>
          )}
        </div>
      </div>

      {/* Return Attribution */}
      {attribution && attribution.positions && attribution.positions.length > 0 && (
        <div className="bg-white rounded-card shadow-card p-6 mb-6">
          <div className="flex items-start justify-between mb-2">
            <h2 className="font-bold text-lg">Return Attribution</h2>
          </div>
          <p className="text-sm text-muted mb-2">
            Portfolio return ({selectedRange.label}): {attribution.total_return >= 0 ? "+" : ""}
            {(attribution.total_return * 100).toFixed(2)}%
          </p>
          <p className="text-xs text-gray-500 mb-4">
            Note: Attribution uses time-weighted daily returns over the selected period. May differ slightly from cumulative YTD performance due to portfolio rebalancing, cash flows, or weighting methodology.
          </p>

          {/* Column Headers */}
          <div className="flex items-center gap-4 mb-2 pb-2 border-b border-gray-200">
            <div className="w-20 text-xs font-semibold text-muted">Symbol</div>
            <div className="w-16 text-xs font-semibold text-muted text-right">
              Avg Weight<br/>(%)
            </div>
            <div className="flex-1 text-xs font-semibold text-muted">
              Contribution to Portfolio
            </div>
            <div className="w-20 text-xs font-semibold text-muted text-right">
              Asset<br/>Return (%)
            </div>
            <div className="w-24 text-xs font-semibold text-muted text-right">
              Contribution<br/>(pp)
            </div>
          </div>

          <div className="space-y-3">
            {attribution.positions.map((pos: any) => {
              const maxContribution = Math.max(
                ...attribution.positions.map((p: any) => Math.abs(p.contribution))
              );
              return (
                <div key={pos.symbol} className="flex items-center gap-4">
                  <Link
                    href={`/company/${pos.symbol}?portfolio_id=${portfolio.id}&portfolio_name=${encodeURIComponent(portfolio.name)}`}
                    className="w-20 text-sm font-semibold text-[#191970] hover:underline"
                  >
                    {pos.symbol}
                  </Link>
                  <div className="w-16 text-xs text-muted text-right">
                    {(pos.weight * 100).toFixed(1)}%
                  </div>
                  <div className="flex-1">
                    <div className="bg-gray-100 rounded-full h-6 overflow-hidden relative">
                      <div
                        className={`h-full ${pos.contribution >= 0 ? "bg-accent-green" : "bg-accent-red"}`}
                        style={{
                          width: `${(Math.abs(pos.contribution) / maxContribution) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                  <div className="w-20 text-sm text-right">
                    {pos.return >= 0 ? "+" : ""}
                    {(pos.return * 100).toFixed(1)}%
                  </div>
                  <div className={`w-24 text-sm font-semibold text-right ${pos.contribution >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                    {pos.contribution >= 0 ? "+" : ""}
                    {(pos.contribution * 100).toFixed(1)}pp
                  </div>
                </div>
              );
            })}
          </div>

          {/* Key Driver Analysis */}
          {(() => {
            const topContributor = attribution.positions[0];
            const positiveContributions = attribution.positions.filter((p: any) => p.contribution > 0);
            const negativeContributions = attribution.positions.filter((p: any) => p.contribution < 0);
            const totalPositive = positiveContributions.reduce((sum: number, p: any) => sum + p.contribution, 0);
            const totalNegative = negativeContributions.reduce((sum: number, p: any) => sum + p.contribution, 0);
            const contributionPct = (topContributor.contribution / attribution.total_return) * 100;

            return (
              <div className="mt-4 p-4 bg-blue-50 rounded-lg text-sm space-y-2">
                <div className="font-semibold text-base mb-2">Key Driver Analysis</div>
                {contributionPct > 100 ? (
                  <>
                    <p>
                      <strong>{topContributor.symbol}</strong> generated{" "}
                      <span className="text-accent-green font-semibold">
                        +{(topContributor.contribution * 100).toFixed(1)}pp
                      </span>{" "}
                      ({contributionPct.toFixed(0)}%+ of net portfolio gains), while other positions were net detractors.
                    </p>
                    <div className="text-xs text-muted pt-2 border-t border-blue-200">
                      Breakdown: {topContributor.symbol} (+{(topContributor.contribution * 100).toFixed(1)}pp){" "}
                      {negativeContributions.length > 0 && `+ Others (${(totalNegative * 100).toFixed(1)}pp)`} = Net (+{(attribution.total_return * 100).toFixed(1)}pp)
                    </div>
                  </>
                ) : topContributor.contribution < 0 ? (
                  <p>
                    All positions contributed negatively. <strong>{topContributor.symbol}</strong> was the least detrimental at{" "}
                    <span className="text-accent-red font-semibold">
                      {(topContributor.contribution * 100).toFixed(1)}pp
                    </span>.
                  </p>
                ) : (
                  <>
                    <p>
                      <strong>{topContributor.symbol}</strong> was the primary driver, contributing{" "}
                      <span className="text-accent-green font-semibold">
                        +{(topContributor.contribution * 100).toFixed(1)}pp
                      </span>{" "}
                      ({contributionPct.toFixed(0)}% of portfolio returns).
                    </p>
                    {(() => {
                      const topPositive = positiveContributions.slice(0, 2);
                      const topNegative = negativeContributions.slice(0, 2);
                      const hasNegatives = topNegative.length > 0;

                      return (
                        <div className="text-xs text-muted pt-2 border-t border-blue-200">
                          {attribution.total_return < 0 ? (
                            <>
                              Losses were driven primarily by{" "}
                              {topNegative.map((p: any, i: number) => (
                                <span key={p.symbol}>
                                  <strong>{p.symbol}</strong>
                                  {i < topNegative.length - 1 ? " and " : ""}
                                </span>
                              ))}, which together accounted for ~{Math.abs(topNegative.reduce((sum: number, p: any) => sum + p.contribution, 0) * 100).toFixed(0)}pp of drawdown
                              {topPositive.length > 0 && (
                                <>
                                  , partially offset by{" "}
                                  {topPositive.map((p: any, i: number) => (
                                    <span key={p.symbol}>
                                      <strong>{p.symbol}</strong>
                                      {i < topPositive.length - 1 ? " and " : ""}
                                    </span>
                                  ))}
                                </>
                              )}.
                            </>
                          ) : (
                            <>
                              Returns were driven by{" "}
                              {topPositive.map((p: any, i: number) => (
                                <span key={p.symbol}>
                                  <strong>{p.symbol}</strong>
                                  {i < topPositive.length - 1 ? " and " : ""}
                                </span>
                              ))}, contributing {(topPositive.reduce((sum: number, p: any) => sum + p.contribution, 0) * 100).toFixed(1)}pp combined
                              {hasNegatives && (
                                <>
                                  , partially offset by{" "}
                                  {topNegative.map((p: any, i: number) => (
                                    <span key={p.symbol}>
                                      <strong>{p.symbol}</strong>
                                      {i < topNegative.length - 1 ? " and " : ""}
                                    </span>
                                  ))}
                                </>
                              )}.
                            </>
                          )}
                        </div>
                      );
                    })()}
                  </>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {/* Holdings Table with Weights */}
      {holdings && holdings.holdings && holdings.holdings.length > 0 && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h2 className="font-bold text-lg mb-2">Holdings</h2>
          <p className="text-sm text-muted mb-4">
            Total Value: <span className="font-semibold">${Number(holdings.total_value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-3 font-semibold text-muted">
                    Symbol
                  </th>
                  <th className="text-right py-3 font-semibold text-muted">
                    Quantity
                  </th>
                  <th className="text-right py-3 font-semibold text-muted">
                    Price
                  </th>
                  <th className="text-right py-3 font-semibold text-muted">
                    Market Value
                  </th>
                  <th className="text-right py-3 font-semibold text-muted">
                    % of Portfolio
                  </th>
                </tr>
              </thead>
              <tbody>
                {holdings.holdings.map((holding: any) => (
                  <tr
                    key={holding.symbol}
                    className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors"
                  >
                    <td className="py-3">
                      <Link
                        href={`/company/${holding.symbol}?portfolio_id=${portfolio.id}&portfolio_name=${encodeURIComponent(portfolio.name)}`}
                        className="font-semibold text-[#191970] hover:underline"
                      >
                        {holding.symbol}
                      </Link>
                    </td>
                    <td className="py-3 text-right">
                      {Number(holding.quantity).toLocaleString()}
                    </td>
                    <td className="py-3 text-right">
                      ${Number(holding.current_price).toFixed(2)}
                    </td>
                    <td className="py-3 text-right">
                      ${Number(holding.market_value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-20 text-right font-semibold">
                          {holding.weight_pct.toFixed(1)}%
                        </div>
                        <div className="w-16 bg-gray-100 rounded-full h-2 overflow-hidden">
                          <div
                            className="h-full bg-primary"
                            style={{ width: `${holding.weight_pct}%` }}
                          />
                        </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
