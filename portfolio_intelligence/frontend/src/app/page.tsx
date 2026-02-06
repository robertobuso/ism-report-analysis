"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { PlusCircle, TrendingUp, BarChart3 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/providers/auth-provider";
import { PortfolioSummary } from "@/lib/types";

export default function HomePage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const { data: portfolios, isLoading } = useQuery<PortfolioSummary[]>({
    queryKey: ["portfolios"],
    queryFn: api.listPortfolios,
    enabled: isAuthenticated,
  });

  if (authLoading || isLoading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-gray-200 rounded w-64" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-40 bg-gray-200 rounded-card" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] px-6">
        <TrendingUp size={48} className="text-primary mb-4" />
        <h1 className="text-2xl font-bold text-primary mb-2">
          Portfolio Intelligence
        </h1>
        <p className="text-muted mb-6 text-center max-w-md">
          A calm, precise, and trustworthy portfolio analytics workspace.
        </p>
        <Link
          href="/login"
          className="bg-primary text-white px-6 py-3 rounded-button font-semibold hover:bg-primary-hover transition-colors"
        >
          Connect with TradeStation
        </Link>
      </div>
    );
  }

  if (!portfolios?.length) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] px-6">
        <BarChart3 size={48} className="text-accent-blue mb-4" />
        <h2 className="text-xl font-bold mb-2">
          Let&apos;s define your first portfolio.
        </h2>
        <p className="text-muted mb-6 text-center max-w-md">
          Create a portfolio to start tracking performance, comparing
          strategies, and understanding what drives returns.
        </p>
        <Link
          href="/portfolios/new"
          className="bg-primary text-white px-6 py-3 rounded-button font-semibold hover:bg-primary-hover transition-colors flex items-center gap-2"
        >
          <PlusCircle size={18} />
          Create Portfolio
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Your Portfolios</h1>
        <Link
          href="/portfolios/new"
          className="bg-primary text-white px-4 py-2 rounded-button font-semibold text-sm hover:bg-primary-hover transition-colors flex items-center gap-2"
        >
          <PlusCircle size={16} />
          New Portfolio
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {portfolios.map((p) => (
          <Link
            key={p.id}
            href={`/portfolios/${p.id}`}
            className="bg-white rounded-card shadow-card p-5 hover:shadow-hover hover:-translate-y-0.5 transition-all block"
          >
            <h3 className="font-bold text-lg mb-1">{p.name}</h3>
            <p className="text-muted text-sm mb-3">{p.base_currency}</p>
            <div className="flex items-center gap-4 text-sm text-muted">
              <span>{p.position_count} holdings</span>
              <span>v{p.version_count}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
