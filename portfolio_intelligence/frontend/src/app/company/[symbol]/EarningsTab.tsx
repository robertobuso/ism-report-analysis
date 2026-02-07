"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { TrendingUp, TrendingDown, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import type { EarningsResponse } from "@/lib/types";

interface EarningsTabProps {
  symbol: string;
}

export default function EarningsTab({ symbol }: EarningsTabProps) {
  const { data: earnings, isLoading } = useQuery<EarningsResponse>({
    queryKey: ["company-earnings", symbol],
    queryFn: () => api.getCompanyEarnings(symbol),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-64 mb-4"></div>
          <div className="h-64 bg-gray-200 rounded mb-6"></div>
          <div className="grid grid-cols-3 gap-4">
            <div className="h-32 bg-gray-200 rounded"></div>
            <div className="h-32 bg-gray-200 rounded"></div>
            <div className="h-32 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (!earnings) {
    return (
      <div className="text-center py-12 text-gray-500">
        No earnings data available for {symbol}
      </div>
    );
  }

  // Prepare chart data
  const chartData = earnings.quarterly.map((q) => ({
    date: q.fiscal_date,
    reported: q.reported_eps,
    estimated: q.estimated_eps,
    surprise: q.surprise_pct,
  }));

  // Calculate stats
  const totalBeats = earnings.quarterly.filter((q) => q.surprise > 0).length;
  const totalMisses = earnings.quarterly.filter((q) => q.surprise < 0).length;
  const totalMeets = earnings.quarterly.filter((q) => q.surprise === 0).length;

  return (
    <div className="space-y-6">
      {/* Header Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Beat Rate */}
        <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-green-800">Beat Rate</span>
            <TrendingUp size={20} className="text-green-600" />
          </div>
          <div className="text-2xl font-bold text-green-900">
            {(earnings.beat_rate * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-green-700 mt-1">
            {totalBeats} of {earnings.quarterly.length} quarters
          </div>
        </div>

        {/* Next Earnings Date */}
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-blue-800">
              Next Report
            </span>
            <Calendar size={20} className="text-blue-600" />
          </div>
          <div className="text-lg font-bold text-blue-900">
            {earnings.next_earnings_date || "TBA"}
          </div>
          <div className="text-xs text-blue-700 mt-1">Expected date</div>
        </div>

        {/* Analyst Coverage */}
        <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-purple-800">
              Analysts
            </span>
            <TrendingUp size={20} className="text-purple-600" />
          </div>
          <div className="text-2xl font-bold text-purple-900">
            {earnings.analyst_count || "N/A"}
          </div>
          <div className="text-xs text-purple-700 mt-1">Following</div>
        </div>

        {/* Miss Rate */}
        <div className="bg-gradient-to-br from-red-50 to-red-100 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-red-800">Miss Rate</span>
            <TrendingDown size={20} className="text-red-600" />
          </div>
          <div className="text-2xl font-bold text-red-900">
            {((totalMisses / earnings.quarterly.length) * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-red-700 mt-1">
            {totalMisses} of {earnings.quarterly.length} quarters
          </div>
        </div>
      </div>

      {/* EPS Trend Chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">
          Earnings Per Share Trend
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey="reported"
              stroke="#191970"
              strokeWidth={2}
              name="Reported EPS"
              dot={{ fill: "#191970", r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="estimated"
              stroke="#dc3545"
              strokeWidth={2}
              strokeDasharray="5 5"
              name="Estimated EPS"
              dot={{ fill: "#dc3545", r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Surprise % Chart */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">
          Earnings Surprise (%)
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <ReferenceLine y={0} stroke="#000" />
            <Bar
              dataKey="surprise"
              fill="#28a745"
              name="Surprise %"
              shape={(props: any) => {
                const { x, y, width, height, value } = props;
                const fill = value >= 0 ? "#28a745" : "#dc3545";
                return (
                  <rect
                    x={x}
                    y={y}
                    width={width}
                    height={height}
                    fill={fill}
                  />
                );
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Quarterly Earnings Table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-bold text-gray-900">
            Quarterly Earnings History
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left font-semibold text-gray-900">
                  Fiscal Date
                </th>
                <th className="px-6 py-3 text-left font-semibold text-gray-900">
                  Report Date
                </th>
                <th className="px-6 py-3 text-right font-semibold text-gray-900">
                  Reported EPS
                </th>
                <th className="px-6 py-3 text-right font-semibold text-gray-900">
                  Estimated EPS
                </th>
                <th className="px-6 py-3 text-right font-semibold text-gray-900">
                  Surprise
                </th>
                <th className="px-6 py-3 text-right font-semibold text-gray-900">
                  Surprise %
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {earnings.quarterly.map((q) => (
                <tr key={q.fiscal_date} className="hover:bg-gray-50">
                  <td className="px-6 py-4 font-medium text-gray-900">
                    {q.fiscal_date}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {q.reported_date || "N/A"}
                  </td>
                  <td className="px-6 py-4 text-right font-semibold text-gray-900">
                    ${q.reported_eps.toFixed(2)}
                  </td>
                  <td className="px-6 py-4 text-right text-gray-600">
                    ${q.estimated_eps.toFixed(2)}
                  </td>
                  <td
                    className={`px-6 py-4 text-right font-semibold ${
                      q.surprise >= 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {q.surprise >= 0 ? "+" : ""}${q.surprise.toFixed(2)}
                  </td>
                  <td
                    className={`px-6 py-4 text-right font-bold ${
                      q.surprise_pct >= 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {q.surprise_pct >= 0 ? "+" : ""}
                    {q.surprise_pct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
