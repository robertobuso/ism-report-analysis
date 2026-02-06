"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { PlusCircle, X, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { AllocationType, PositionCreate, PortfolioCreate } from "@/lib/types";

export default function NewPortfolioPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [allocationType, setAllocationType] =
    useState<AllocationType>("weight");
  const [positions, setPositions] = useState<PositionCreate[]>([]);
  const [symbolInput, setSymbolInput] = useState("");
  const [valueInput, setValueInput] = useState("");

  const totalWeight = positions.reduce((sum, p) => sum + p.value, 0);
  const weightWarning =
    allocationType === "weight" &&
    positions.length > 0 &&
    Math.abs(totalWeight - 1) > 0.001;

  const addPosition = useCallback(() => {
    const symbol = symbolInput.trim().toUpperCase();
    const value = parseFloat(valueInput);
    if (!symbol || isNaN(value) || value <= 0) return;
    if (positions.some((p) => p.symbol === symbol)) return;

    setPositions((prev) => [
      ...prev,
      { symbol, allocation_type: allocationType, value },
    ]);
    setSymbolInput("");
    setValueInput("");
  }, [symbolInput, valueInput, allocationType, positions]);

  const removePosition = (symbol: string) => {
    setPositions((prev) => prev.filter((p) => p.symbol !== symbol));
  };

  const createMutation = useMutation({
    mutationFn: (data: PortfolioCreate) => api.createPortfolio(data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      router.push(`/portfolios/${data.id}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || positions.length === 0) return;

    createMutation.mutate({
      name: name.trim(),
      base_currency: "USD",
      allocation_type: allocationType,
      positions,
      note: description.trim() || undefined,
    });
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold mb-6">Create Portfolio</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-semibold mb-1">
            Portfolio Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Long-term Growth"
            className="w-full border border-gray-200 rounded-button px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-semibold mb-1">
            Description{" "}
            <span className="text-muted font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Dividend focus, low volatility"
            className="w-full border border-gray-200 rounded-button px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
          />
        </div>

        <div>
          <label className="block text-sm font-semibold mb-2">
            Allocation Mode
          </label>
          <div className="flex rounded-button border border-gray-200 overflow-hidden">
            <button
              type="button"
              onClick={() => setAllocationType("weight")}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                allocationType === "weight"
                  ? "bg-primary text-white"
                  : "bg-white text-foreground hover:bg-gray-50"
              }`}
            >
              Weight (%)
            </button>
            <button
              type="button"
              onClick={() => setAllocationType("quantity")}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                allocationType === "quantity"
                  ? "bg-primary text-white"
                  : "bg-white text-foreground hover:bg-gray-50"
              }`}
            >
              Quantity (shares)
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold mb-2">Holdings</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              placeholder="Symbol (e.g. AAPL)"
              className="flex-1 border border-gray-200 rounded-button px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addPosition();
                }
              }}
            />
            <input
              type="number"
              value={valueInput}
              onChange={(e) => setValueInput(e.target.value)}
              placeholder={allocationType === "weight" ? "0.25" : "100"}
              step="any"
              min="0"
              className="w-28 border border-gray-200 rounded-button px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addPosition();
                }
              }}
            />
            <button
              type="button"
              onClick={addPosition}
              className="bg-accent-blue text-white px-3 py-2.5 rounded-button hover:opacity-90 transition-opacity"
            >
              <PlusCircle size={18} />
            </button>
          </div>
        </div>

        {allocationType === "weight" && positions.length > 0 && (
          <div>
            <div className="flex justify-between text-xs text-muted mb-1">
              <span>Allocation</span>
              <span>{(totalWeight * 100).toFixed(1)}%</span>
            </div>
            <div className="h-3 bg-gray-100 rounded-full overflow-hidden flex">
              <AnimatePresence>
                {positions.map((p) => (
                  <motion.div
                    key={p.symbol}
                    initial={{ width: 0 }}
                    animate={{ width: `${p.value * 100}%` }}
                    exit={{ width: 0 }}
                    className="h-full bg-accent-blue first:rounded-l-full last:rounded-r-full"
                    style={{ minWidth: positions.length > 0 ? "2px" : 0 }}
                  />
                ))}
              </AnimatePresence>
            </div>
            {weightWarning && (
              <div className="flex items-center gap-1.5 mt-2 text-xs text-accent-warning">
                <AlertTriangle size={14} />
                Weights sum to {(totalWeight * 100).toFixed(1)}% — expected 100%
              </div>
            )}
          </div>
        )}

        <AnimatePresence>
          {positions.map((p) => (
            <motion.div
              key={p.symbol}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-button px-4 py-3"
            >
              <div>
                <span className="font-semibold">{p.symbol}</span>
                <span className="text-muted ml-2 text-sm">
                  {allocationType === "weight"
                    ? `${(p.value * 100).toFixed(1)}%`
                    : `${p.value} shares`}
                </span>
              </div>
              <button
                type="button"
                onClick={() => removePosition(p.symbol)}
                className="text-muted hover:text-accent-red transition-colors"
              >
                <X size={16} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>

        <button
          type="submit"
          disabled={
            !name.trim() || positions.length === 0 || createMutation.isPending
          }
          className="w-full bg-primary text-white py-3 rounded-button font-semibold hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {createMutation.isPending ? "Creating..." : "Create Portfolio"}
        </button>

        {createMutation.isError && (
          <p className="text-accent-red text-sm text-center">
            {createMutation.error?.message || "Failed to create portfolio"}
          </p>
        )}
      </form>
    </div>
  );
}
