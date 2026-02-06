"use client";

import { TrendingUp, Shield, Eye } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const handleLogin = () => {
    window.location.href = `${API_BASE}/api/v1/auth/login`;
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] px-6">
      <TrendingUp size={56} className="text-primary mb-6" />
      <h1 className="text-3xl font-bold text-primary mb-2">
        Portfolio Intelligence
      </h1>
      <p className="text-muted mb-8 text-center max-w-md">
        Connect your TradeStation account to build persistent, analyzable
        portfolio workspaces.
      </p>

      <button
        onClick={handleLogin}
        className="bg-primary text-white px-8 py-3 rounded-button font-semibold text-lg hover:bg-primary-hover transition-all hover:-translate-y-0.5"
      >
        Connect with TradeStation
      </button>

      <div className="mt-10 flex flex-col sm:flex-row gap-6 text-sm text-muted">
        <div className="flex items-center gap-2">
          <Eye size={16} className="text-accent-green" />
          <span>Read-only access</span>
        </div>
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-accent-green" />
          <span>No trades, ever</span>
        </div>
      </div>
    </div>
  );
}
