"use client";

import { useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CompanyHeader,
  InsightCard,
  CompanyOverview,
} from "@/lib/types";
import FinancialsTab from "./FinancialsTab";
import EarningsTab from "./EarningsTab";
import NewsTab from "./NewsTab";
import TechnicalsTab from "./TechnicalsTab";
import PortfolioImpactTab from "./PortfolioImpactTab";

interface PageProps {
  params: { symbol: string };
}

export default function CompanyPage({ params }: PageProps) {
  const symbol = params.symbol.toUpperCase();
  const searchParams = useSearchParams();
  const router = useRouter();
  const portfolioId = searchParams.get("portfolio_id");
  const portfolioName = searchParams.get("portfolio_name");

  const [activeTab, setActiveTab] = useState<string>("overview");

  // Fetch header data
  const { data: header, isLoading: headerLoading } = useQuery<CompanyHeader>({
    queryKey: ["company-header", symbol, portfolioId],
    queryFn: () => api.getCompanyHeader(symbol, portfolioId || undefined),
  });

  // Fetch insights
  const { data: insights, isLoading: insightsLoading } = useQuery<InsightCard[]>({
    queryKey: ["company-insights", symbol, portfolioId],
    queryFn: () => api.getCompanyInsights(symbol, portfolioId || undefined),
  });

  // Fetch overview (default tab)
  const { data: overview, isLoading: overviewLoading } = useQuery<CompanyOverview>({
    queryKey: ["company-overview", symbol],
    queryFn: () => api.getCompanyOverview(symbol),
    enabled: activeTab === "overview",
  });

  if (headerLoading) {
    return (
      <div className="min-h-screen bg-gray-50 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-64 mb-8"></div>
            <div className="bg-white rounded-2xl p-6 shadow-sm mb-6">
              <div className="h-12 bg-gray-200 rounded w-96 mb-4"></div>
              <div className="h-6 bg-gray-200 rounded w-48"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-8 py-4">
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <button
              onClick={() => router.push("/portfolios")}
              className="hover:text-[#191970]"
            >
              Portfolios
            </button>
            {portfolioId && portfolioName && (
              <>
                <span>/</span>
                <button
                  onClick={() => router.push(`/portfolios/${portfolioId}`)}
                  className="hover:text-[#191970]"
                >
                  {portfolioName}
                </button>
              </>
            )}
            <span>/</span>
            <span className="text-[#191970] font-medium">{symbol}</span>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-8 py-6">
        {/* Company Header */}
        {header && (
          <div className="bg-white rounded-2xl p-6 shadow-sm mb-6 sticky top-0 z-10">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">
                  {header.name}
                </h1>
                <div className="flex items-center gap-4 text-sm text-gray-600">
                  <span>{symbol}</span>
                  <span>•</span>
                  <span>{header.exchange}</span>
                  {header.sector && (
                    <>
                      <span>•</span>
                      <span>{header.sector}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-gray-900">
                  ${header.current_price.toFixed(2)}
                </div>
                <div
                  className={`text-sm font-medium ${
                    header.change_amount >= 0
                      ? "text-green-600"
                      : "text-red-600"
                  }`}
                >
                  {header.change_amount >= 0 ? "+" : ""}
                  {header.change_amount.toFixed(2)} ({header.change_percent.toFixed(2)}%)
                </div>
              </div>
            </div>

            {/* Portfolio Context */}
            {portfolioId && header.portfolio_weight !== null && (
              <div className="mt-4 pt-4 border-t grid grid-cols-4 gap-4">
                <div>
                  <div className="text-sm text-gray-600">Portfolio Weight</div>
                  <div className="text-lg font-semibold">
                    {(header.portfolio_weight * 100).toFixed(1)}%
                  </div>
                </div>
                {header.contribution_to_return !== null && (
                  <div>
                    <div className="text-sm text-gray-600">Contribution</div>
                    <div
                      className={`text-lg font-semibold ${
                        header.contribution_to_return >= 0
                          ? "text-green-600"
                          : "text-red-600"
                      }`}
                    >
                      {(header.contribution_to_return * 100).toFixed(2)}pp
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Insight Cards */}
        {insights && insights.length > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-6">
            {insights.map((card, idx) => (
              <button
                key={idx}
                onClick={() => setActiveTab(card.tab_target)}
                className={`bg-white rounded-xl p-6 shadow-sm text-left hover:shadow-md transition-shadow border-l-4 ${
                  card.severity === "positive"
                    ? "border-green-500"
                    : card.severity === "negative"
                      ? "border-red-500"
                      : "border-gray-300"
                }`}
              >
                <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                  {card.type.replace("_", " ")}
                </div>
                <p className="text-sm text-gray-900">{card.summary}</p>
              </button>
            ))}
          </div>
        )}

        {/* Tab Navigation */}
        <div className="bg-white rounded-t-xl shadow-sm sticky top-32 z-10">
          <div className="flex border-b">
            {[
              { id: "overview", label: "Overview" },
              { id: "financials", label: "Financials" },
              { id: "earnings", label: "Earnings" },
              { id: "news", label: "News & Sentiment" },
              { id: "technicals", label: "Price & Technicals" },
              { id: "impact", label: "Portfolio Impact" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-6 py-4 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? "text-[#191970] border-b-2 border-[#191970]"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab Content */}
        <div className="bg-white rounded-b-xl shadow-sm p-8">
          {activeTab === "overview" && overview && (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900 mb-4">
                  About {header?.name}
                </h2>
                <p className="text-gray-700 leading-relaxed mb-4">
                  {overview.description}
                </p>
                <ul className="space-y-2">
                  {overview.business_bullets.map((bullet, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-[#191970]">•</span>
                      <span className="text-gray-700">{bullet}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-4 gap-4">
                {overview.market_cap && (
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="text-sm text-gray-600">Market Cap</div>
                    <div className="text-lg font-semibold">
                      ${(overview.market_cap / 1e12).toFixed(2)}T
                    </div>
                  </div>
                )}
                {overview.pe_ratio && (
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="text-sm text-gray-600">P/E Ratio</div>
                    <div className="text-lg font-semibold">
                      {overview.pe_ratio.toFixed(2)}
                    </div>
                  </div>
                )}
                {overview.profit_margin && (
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="text-sm text-gray-600">Profit Margin</div>
                    <div className="text-lg font-semibold">
                      {(overview.profit_margin * 100).toFixed(1)}%
                    </div>
                  </div>
                )}
                {overview.dividend_yield && (
                  <div className="bg-gray-50 rounded-lg p-4">
                    <div className="text-sm text-gray-600">Dividend Yield</div>
                    <div className="text-lg font-semibold">
                      {(overview.dividend_yield * 100).toFixed(2)}%
                    </div>
                  </div>
                )}
              </div>

              {/* Quality Badges */}
              <div className="flex gap-4">
                {overview.profitability_trend && (
                  <div
                    className={`px-4 py-2 rounded-full text-sm font-medium ${
                      overview.profitability_trend === "improving"
                        ? "bg-green-100 text-green-800"
                        : overview.profitability_trend === "declining"
                          ? "bg-red-100 text-red-800"
                          : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    Profitability: {overview.profitability_trend}
                  </div>
                )}
                {overview.leverage_risk && (
                  <div className="px-4 py-2 rounded-full text-sm font-medium bg-gray-100 text-gray-800">
                    Leverage Risk: {overview.leverage_risk}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "financials" && <FinancialsTab symbol={symbol} />}

          {activeTab === "earnings" && <EarningsTab symbol={symbol} />}

          {activeTab === "news" && <NewsTab symbol={symbol} />}

          {activeTab === "technicals" && <TechnicalsTab symbol={symbol} />}

          {activeTab === "impact" && (
            <PortfolioImpactTab symbol={symbol} portfolioId={portfolioId || ""} />
          )}
        </div>
      </div>
    </div>
  );
}
