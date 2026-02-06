"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
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

export default function PortfolioOverviewPage() {
  const params = useParams();
  const id = params.id as string;
  const { isAuthenticated } = useAuth();
  const [selectedRange, setSelectedRange] = useState(TIME_RANGES[3]); // 1Y default

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

  if (portfolioLoading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-48" />
          <div className="h-64 bg-gray-200 rounded-card" />
        </div>
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-8">
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

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold">{portfolio.name}</h1>
        <p className="text-muted text-sm">{portfolio.base_currency}</p>
      </div>

      {/* Performance Header */}
      <div className="bg-white rounded-card shadow-card p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            {latestNav !== null && (
              <div className="text-3xl font-bold">
                {latestNav.toFixed(2)}
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

      {/* Holdings Table */}
      {portfolio.latest_version && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h2 className="font-bold text-lg mb-4">
            Holdings
            <span className="text-muted text-sm font-normal ml-2">
              v{portfolio.latest_version.version_number}
            </span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-3 font-semibold text-muted">
                    Symbol
                  </th>
                  <th className="text-right py-3 font-semibold text-muted">
                    {portfolio.latest_version.positions[0]?.allocation_type ===
                    "weight"
                      ? "Weight"
                      : "Quantity"}
                  </th>
                </tr>
              </thead>
              <tbody>
                {portfolio.latest_version.positions.map((pos) => (
                  <tr
                    key={pos.id}
                    className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors"
                  >
                    <td className="py-3 font-semibold">{pos.symbol}</td>
                    <td className="py-3 text-right">
                      {pos.allocation_type === "weight"
                        ? `${(Number(pos.value) * 100).toFixed(1)}%`
                        : Number(pos.value).toLocaleString()}
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
