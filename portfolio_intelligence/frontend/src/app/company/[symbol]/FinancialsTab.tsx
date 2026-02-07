"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { ChevronDown, ChevronUp, Download } from "lucide-react";
import { api } from "@/lib/api";
import type { FinancialsResponse } from "@/lib/types";

interface FinancialsTabProps {
  symbol: string;
}

export default function FinancialsTab({ symbol }: FinancialsTabProps) {
  const [period, setPeriod] = useState<"quarterly" | "annual">("quarterly");
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const { data: financials, isLoading } = useQuery<FinancialsResponse>({
    queryKey: ["company-financials", symbol, period],
    queryFn: () => api.getCompanyFinancials(symbol, period),
  });

  const handleDownloadCSV = () => {
    if (!financials) return;

    // Create CSV content
    const rows = [
      ["Fiscal Date", "Revenue", "Net Income", "Operating Income", "Total Assets", "Total Liabilities"],
    ];

    financials.income_statement.forEach((statement, idx) => {
      const balanceSheet = financials.balance_sheet[idx];
      rows.push([
        statement.fiscal_date,
        statement.data.totalRevenue?.toString() || "",
        statement.data.netIncome?.toString() || "",
        statement.data.operatingIncome?.toString() || "",
        balanceSheet?.data.totalAssets?.toString() || "",
        balanceSheet?.data.totalLiabilities?.toString() || "",
      ]);
    });

    const csv = rows.map((row) => row.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${symbol}_financials_${period}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-64 mb-4"></div>
          <div className="h-64 bg-gray-200 rounded mb-6"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (!financials) {
    return (
      <div className="text-center py-12 text-gray-500">
        No financial data available for {symbol}
      </div>
    );
  }

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  return (
    <div className="space-y-6">
      {/* Header with controls */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">
            Financial Statements
          </h2>
          <p className="text-sm text-gray-600 mt-1">{financials.narrative}</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Period Toggle */}
          <div className="flex rounded-lg border border-gray-300 overflow-hidden">
            <button
              onClick={() => setPeriod("quarterly")}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                period === "quarterly"
                  ? "bg-[#191970] text-white"
                  : "bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              Quarterly
            </button>
            <button
              onClick={() => setPeriod("annual")}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                period === "annual"
                  ? "bg-[#191970] text-white"
                  : "bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              Annual
            </button>
          </div>

          {/* Download CSV */}
          <button
            onClick={handleDownloadCSV}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-[#191970] border border-[#191970] rounded-lg hover:bg-[#191970] hover:text-white transition-colors"
          >
            <Download size={16} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Chart */}
        {financials.chart_data.revenue && (
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              Revenue Trend
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={financials.chart_data.revenue}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#191970" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Net Income Chart */}
        {financials.chart_data.net_income && (
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              Net Income
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={financials.chart_data.net_income}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#28a745"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Profit Margin Chart */}
        {financials.chart_data.profit_margin && (
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              Profit Margin (%)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={financials.chart_data.profit_margin}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#764ba2"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Free Cash Flow Chart */}
        {financials.chart_data.free_cash_flow && (
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              Free Cash Flow
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={financials.chart_data.free_cash_flow}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#3b82f6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* ROE Chart */}
        {financials.chart_data.roe && (
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
              Return on Equity (%)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={financials.chart_data.roe}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#dc3545"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Collapsible Statements */}
      <div className="space-y-4">
        {/* Income Statement */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <button
            onClick={() => toggleSection("income")}
            className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
          >
            <h3 className="text-base font-semibold text-gray-900">
              Income Statement
            </h3>
            {expandedSection === "income" ? (
              <ChevronUp size={20} />
            ) : (
              <ChevronDown size={20} />
            )}
          </button>
          {expandedSection === "income" && (
            <div className="border-t border-gray-200 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left font-semibold">Metric</th>
                    {financials.income_statement.slice(0, 4).map((stmt) => (
                      <th key={stmt.fiscal_date} className="px-4 py-2 text-right font-semibold">
                        {stmt.fiscal_date}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  <tr>
                    <td className="px-4 py-2 font-medium">Revenue</td>
                    {financials.income_statement.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.totalRevenue
                          ? `$${(Number(stmt.data.totalRevenue) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Gross Profit</td>
                    {financials.income_statement.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.grossProfit
                          ? `$${(Number(stmt.data.grossProfit) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Operating Income</td>
                    {financials.income_statement.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.operatingIncome
                          ? `$${(Number(stmt.data.operatingIncome) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Net Income</td>
                    {financials.income_statement.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.netIncome
                          ? `$${(Number(stmt.data.netIncome) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Balance Sheet */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <button
            onClick={() => toggleSection("balance")}
            className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
          >
            <h3 className="text-base font-semibold text-gray-900">
              Balance Sheet
            </h3>
            {expandedSection === "balance" ? (
              <ChevronUp size={20} />
            ) : (
              <ChevronDown size={20} />
            )}
          </button>
          {expandedSection === "balance" && (
            <div className="border-t border-gray-200 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left font-semibold">Metric</th>
                    {financials.balance_sheet.slice(0, 4).map((stmt) => (
                      <th key={stmt.fiscal_date} className="px-4 py-2 text-right font-semibold">
                        {stmt.fiscal_date}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  <tr>
                    <td className="px-4 py-2 font-medium">Total Assets</td>
                    {financials.balance_sheet.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.totalAssets
                          ? `$${(Number(stmt.data.totalAssets) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Total Liabilities</td>
                    {financials.balance_sheet.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.totalLiabilities
                          ? `$${(Number(stmt.data.totalLiabilities) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Shareholder Equity</td>
                    {financials.balance_sheet.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.totalShareholderEquity
                          ? `$${(Number(stmt.data.totalShareholderEquity) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Cash Flow Statement */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <button
            onClick={() => toggleSection("cashflow")}
            className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
          >
            <h3 className="text-base font-semibold text-gray-900">
              Cash Flow Statement
            </h3>
            {expandedSection === "cashflow" ? (
              <ChevronUp size={20} />
            ) : (
              <ChevronDown size={20} />
            )}
          </button>
          {expandedSection === "cashflow" && (
            <div className="border-t border-gray-200 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left font-semibold">Metric</th>
                    {financials.cash_flow.slice(0, 4).map((stmt) => (
                      <th key={stmt.fiscal_date} className="px-4 py-2 text-right font-semibold">
                        {stmt.fiscal_date}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  <tr>
                    <td className="px-4 py-2 font-medium">Operating Cash Flow</td>
                    {financials.cash_flow.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.operatingCashflow
                          ? `$${(Number(stmt.data.operatingCashflow) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Capital Expenditure</td>
                    {financials.cash_flow.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.capitalExpenditures
                          ? `$${(Number(stmt.data.capitalExpenditures) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-medium">Free Cash Flow</td>
                    {financials.cash_flow.slice(0, 4).map((stmt) => (
                      <td key={stmt.fiscal_date} className="px-4 py-2 text-right">
                        {stmt.data.operatingCashflow && stmt.data.capitalExpenditures
                          ? `$${((Number(stmt.data.operatingCashflow) + Number(stmt.data.capitalExpenditures)) / 1e9).toFixed(2)}B`
                          : "N/A"}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
