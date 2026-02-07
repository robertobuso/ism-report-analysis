"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, TrendingUp, TrendingDown, Shield, Target } from "lucide-react";
import { api } from "@/lib/api";

interface PortfolioImpactTabProps {
  symbol: string;
  portfolioId: string;
}

interface ConcentrationAlert {
  alert_type: string;
  message: string;
  holdings_involved: string[];
  combined_weight: number;
}

interface HealthScore {
  total: number;
  fundamentals: number;
  price_trend: number;
  sentiment: number;
  portfolio_impact: number;
  breakdown: Record<string, any>;
}

interface PortfolioImpactData {
  contribution_to_return: number;
  risk_contribution: number;
  correlation_with_top_holdings: Record<string, number>;
  sector_overlap: Record<string, number>;
  concentration_alerts: ConcentrationAlert[];
  health_score: HealthScore;
  fetched_at: string;
}

export default function PortfolioImpactTab({ symbol, portfolioId }: PortfolioImpactTabProps) {
  // Fetch portfolio impact data
  const { data: impact, isLoading } = useQuery<PortfolioImpactData>({
    queryKey: ["company-portfolio-impact", symbol, portfolioId],
    queryFn: () => api.getCompanyPortfolioImpact(symbol, portfolioId),
    enabled: !!portfolioId,
  });

  if (!portfolioId) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Shield size={48} className="text-gray-400 mb-4" />
        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          Portfolio Context Required
        </h3>
        <p className="text-sm text-gray-600 text-center max-w-md">
          View this company from a portfolio to see position-specific insights,
          risk analysis, and concentration alerts.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-48 bg-gray-200 rounded-lg mb-6"></div>
          <div className="grid grid-cols-2 gap-4 mb-6">
            {[1, 2].map((i) => (
              <div key={i} className="h-32 bg-gray-200 rounded-lg"></div>
            ))}
          </div>
          <div className="h-64 bg-gray-200 rounded-lg"></div>
        </div>
      </div>
    );
  }

  if (!impact) {
    return (
      <div className="text-center py-12 text-gray-500">
        No portfolio impact data available
      </div>
    );
  }

  // Calculate health score color
  const getHealthScoreColor = (score: number) => {
    if (score >= 75) return "text-green-600 bg-green-50";
    if (score >= 50) return "text-yellow-600 bg-yellow-50";
    return "text-red-600 bg-red-50";
  };

  const healthScoreColor = getHealthScoreColor(impact.health_score.total);

  return (
    <div className="space-y-6">
      {/* Concentration Alerts */}
      {impact.concentration_alerts.length > 0 && (
        <div className="space-y-3">
          {impact.concentration_alerts.map((alert, idx) => (
            <div
              key={idx}
              className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3"
            >
              <AlertTriangle className="text-amber-600 flex-shrink-0 mt-0.5" size={20} />
              <div>
                <h4 className="text-sm font-semibold text-amber-900 mb-1">
                  {alert.alert_type === "sector_overlap"
                    ? "Sector Concentration"
                    : alert.alert_type === "position_size"
                    ? "Large Position"
                    : "Theme Overlap"}
                </h4>
                <p className="text-sm text-amber-800 mb-2">{alert.message}</p>
                <div className="flex items-center gap-2 text-xs text-amber-700">
                  <span className="font-medium">
                    Combined Weight: {(alert.combined_weight * 100).toFixed(1)}%
                  </span>
                  <span>•</span>
                  <span>{alert.holdings_involved.join(", ")}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Position Health Score */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-base font-semibold text-gray-900 mb-1">
              Position Health Score
            </h3>
            <p className="text-sm text-gray-600">
              Composite score across fundamentals, technicals, sentiment, and portfolio fit
            </p>
          </div>
          <div className={`text-center px-6 py-4 rounded-lg ${healthScoreColor}`}>
            <div className="text-4xl font-bold mb-1">
              {impact.health_score.total.toFixed(0)}
            </div>
            <div className="text-xs font-medium uppercase tracking-wide">
              {impact.health_score.total >= 75
                ? "Strong"
                : impact.health_score.total >= 50
                ? "Moderate"
                : "Weak"}
            </div>
          </div>
        </div>

        {/* Score Breakdown */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900 mb-1">
              {impact.health_score.fundamentals.toFixed(0)}
            </div>
            <div className="text-xs text-gray-600">Fundamentals</div>
            <div className="text-xs text-gray-500 mt-1">/25</div>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900 mb-1">
              {impact.health_score.price_trend.toFixed(0)}
            </div>
            <div className="text-xs text-gray-600">Price Trend</div>
            <div className="text-xs text-gray-500 mt-1">/25</div>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900 mb-1">
              {impact.health_score.sentiment.toFixed(0)}
            </div>
            <div className="text-xs text-gray-600">Sentiment</div>
            <div className="text-xs text-gray-500 mt-1">/25</div>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900 mb-1">
              {impact.health_score.portfolio_impact.toFixed(0)}
            </div>
            <div className="text-xs text-gray-600">Portfolio Fit</div>
            <div className="text-xs text-gray-500 mt-1">/25</div>
          </div>
        </div>
      </div>

      {/* Contribution Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900 mb-1">
                Contribution to Return
              </h3>
              <p className="text-xs text-gray-600">
                Impact on portfolio performance
              </p>
            </div>
            {impact.contribution_to_return > 0 ? (
              <TrendingUp className="text-green-600" size={24} />
            ) : (
              <TrendingDown className="text-red-600" size={24} />
            )}
          </div>
          <div
            className={`text-3xl font-bold ${
              impact.contribution_to_return > 0 ? "text-green-600" : "text-red-600"
            }`}
          >
            {impact.contribution_to_return > 0 ? "+" : ""}
            {(impact.contribution_to_return * 100).toFixed(2)}%
          </div>
          <p className="text-xs text-gray-500 mt-2">
            This position contributed{" "}
            {impact.contribution_to_return > 0 ? "positively" : "negatively"} to your
            portfolio's overall return
          </p>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900 mb-1">
                Risk Contribution
              </h3>
              <p className="text-xs text-gray-600">
                Contribution to portfolio volatility
              </p>
            </div>
            <Target className="text-blue-600" size={24} />
          </div>
          <div className="text-3xl font-bold text-gray-900">
            {(impact.risk_contribution * 100).toFixed(2)}%
          </div>
          <p className="text-xs text-gray-500 mt-2">
            This position accounts for {(impact.risk_contribution * 100).toFixed(1)}% of
            your portfolio's total risk
          </p>
        </div>
      </div>

      {/* Sector Overlap */}
      {Object.keys(impact.sector_overlap).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">
            Sector Overlap with Other Holdings
          </h3>
          <div className="space-y-3">
            {Object.entries(impact.sector_overlap).map(([sector, weight]) => {
              // Normalize the weight value (handle if it's already a percentage or decimal)
              const displayWeight = weight > 1 ? weight : weight * 100;
              const barWidth = Math.min(displayWeight, 100); // Cap at 100%

              return (
                <div key={sector}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-700">{sector}</span>
                    <span className="text-sm font-medium text-gray-900">
                      {displayWeight.toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full"
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Correlation with Top Holdings */}
      {Object.keys(impact.correlation_with_top_holdings).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">
            Correlation with Top Holdings
          </h3>
          <p className="text-xs text-gray-600 mb-4">
            Higher correlation means this position tends to move in the same direction as
            these holdings
          </p>
          <div className="space-y-3">
            {Object.entries(impact.correlation_with_top_holdings).map(
              ([holdingSymbol, correlation]) => {
                // Correlation should be between -1 and 1
                const normalizedCorr = correlation > 1 ? correlation / 100 : correlation;
                const absCorr = Math.abs(normalizedCorr);

                return (
                  <div key={holdingSymbol}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-700">
                        {holdingSymbol}
                      </span>
                      <span
                        className={`text-sm font-semibold ${
                          absCorr > 0.7
                            ? "text-red-600"
                            : absCorr > 0.3
                            ? "text-yellow-600"
                            : "text-green-600"
                        }`}
                      >
                        {normalizedCorr.toFixed(2)}
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${
                          absCorr > 0.7
                            ? "bg-red-600"
                            : absCorr > 0.3
                            ? "bg-yellow-600"
                            : "bg-green-600"
                        }`}
                        style={{ width: `${Math.min(absCorr * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              }
            )}
          </div>
          <p className="text-xs text-gray-500 mt-4">
            <span className="text-red-600 font-medium">High correlation (&gt;0.7)</span>{" "}
            increases concentration risk •{" "}
            <span className="text-green-600 font-medium">Low correlation (&lt;0.3)</span>{" "}
            provides diversification
          </p>
        </div>
      )}
    </div>
  );
}
