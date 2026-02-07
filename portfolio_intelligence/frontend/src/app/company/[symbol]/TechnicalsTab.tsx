"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";
import { TrendingUp, TrendingDown, Activity } from "lucide-react";
import { api } from "@/lib/api";

interface TechnicalsTabProps {
  symbol: string;
}

interface PriceData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export default function TechnicalsTab({ symbol }: TechnicalsTabProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [timeframe, setTimeframe] = useState<"1M" | "3M" | "6M" | "1Y">("3M");

  // Fetch price data from Alpha Vantage
  const { data: priceData, isLoading: priceLoading } = useQuery({
    queryKey: ["company-prices", symbol, timeframe],
    queryFn: () => api.getCompanyPrices(symbol, "compact"),
  });

  // Fetch technical indicators (calculated from price data)
  const { data: technicals, isLoading: techLoading } = useQuery({
    queryKey: ["company-technicals", symbol],
    queryFn: () => api.getCompanyTechnicals(symbol),
  });

  // Initialize chart once
  useEffect(() => {
    if (!chartContainerRef.current || chartRef.current) return;

    console.log("🎨 Initializing chart...");
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#333",
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      grid: {
        vertLines: { color: "#f0f0f0" },
        horzLines: { color: "#f0f0f0" },
      },
      timeScale: {
        borderColor: "#d1d4dc",
      },
      rightPriceScale: {
        borderColor: "#d1d4dc",
      },
    });

    chartRef.current = chart;

    // Create the candlestick series once
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    seriesRef.current = candlestickSeries;
    console.log("✅ Chart and series initialized");

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener("resize", handleResize);

    // Cleanup function
    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }
    };
  }, []);

  // Update chart data when priceData or timeframe changes
  useEffect(() => {
    console.log("📊 Data update effect triggered");
    console.log("📊 Price data received:", priceData);
    console.log("📊 Has seriesRef:", !!seriesRef.current);
    console.log("📊 Bars count:", priceData?.bars?.length);

    if (!seriesRef.current || !priceData || !priceData.bars || priceData.bars.length === 0) {
      console.log("⚠️ Chart update skipped - missing requirements or no data");
      return;
    }

    // Convert Alpha Vantage data to lightweight-charts format
    const allCandlestickData = priceData.bars
      .map((bar: any) => ({
        time: bar.TimeStamp.split("T")[0], // Format: "2026-02-07"
        open: bar.Open,
        high: bar.High,
        low: bar.Low,
        close: bar.Close,
      }));

    console.log("📊 All candlestick data count:", allCandlestickData.length);
    console.log("📊 First bar:", allCandlestickData[0]);
    console.log("📊 Last bar:", allCandlestickData[allCandlestickData.length - 1]);

    // Filter based on timeframe
    const daysToShow = timeframe === "1M" ? 30 : timeframe === "3M" ? 90 : timeframe === "6M" ? 180 : 365;
    const startIndex = Math.max(0, allCandlestickData.length - daysToShow);
    const candlestickData = allCandlestickData.slice(startIndex);

    console.log("📊 Days to show:", daysToShow);
    console.log("📊 Start index:", startIndex);
    console.log("📊 Filtered data count:", candlestickData.length);
    console.log("📊 Filtered data sample:", candlestickData.slice(0, 2));

    try {
      // Update the existing series with new data
      seriesRef.current.setData(candlestickData);

      // Fit content
      if (chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }

      console.log("✅ Chart updated successfully");
    } catch (error) {
      console.error("❌ Error updating chart:", error);
    }
  }, [priceData, timeframe]);


  if (priceLoading || techLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-64 mb-4"></div>
          <div className="h-96 bg-gray-200 rounded mb-6"></div>
          <div className="grid grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Calculate key levels from real data
  const currentPrice = priceData?.bars?.[priceData.bars.length - 1]?.Close || 0;
  const week52High = priceData?.bars
    ? Math.max(...priceData.bars.map((b: any) => b.High))
    : currentPrice * 1.25;
  const week52Low = priceData?.bars
    ? Math.min(...priceData.bars.map((b: any) => b.Low))
    : currentPrice * 0.75;

  // Extract technical indicators from API response
  const rsiData = technicals?.indicators?.find((i: any) => i.indicator === "RSI");
  const macdData = technicals?.indicators?.find((i: any) => i.indicator === "MACD");
  const smaData = technicals?.indicators?.find((i: any) => i.indicator === "SMA");
  const bbandsData = technicals?.indicators?.find((i: any) => i.indicator === "BBANDS");

  const rsiValue = rsiData?.values?.[0]?.value || 50;
  const macdValue = macdData?.values?.[0];
  const sma50 = smaData?.values?.[0]?.SMA_50 || currentPrice;
  const sma200 = smaData?.values?.[0]?.SMA_200 || currentPrice;
  const bbands = bbandsData?.values?.[0];

  // Build indicator cards with real data
  const indicators = [
    {
      name: "RSI (14)",
      value: rsiValue.toFixed(1),
      signal: rsiValue > 70 ? "Overbought" : rsiValue < 30 ? "Oversold" : "Neutral",
      color: rsiValue > 70 ? "text-red-700" : rsiValue < 30 ? "text-green-700" : "text-gray-700",
      bgColor: rsiValue > 70 ? "bg-red-50" : rsiValue < 30 ? "bg-green-50" : "bg-gray-100",
      description: `RSI at ${rsiValue.toFixed(1)} - ${rsiValue > 70 ? "overbought conditions" : rsiValue < 30 ? "oversold conditions" : "balanced momentum"}`,
    },
    {
      name: "MACD",
      value: macdValue ? `${macdValue.macd > 0 ? "+" : ""}${macdValue.macd.toFixed(4)}` : "N/A",
      signal: macdValue && macdValue.macd > macdValue.signal ? "Bullish" : "Bearish",
      color: macdValue && macdValue.macd > macdValue.signal ? "text-green-700" : "text-red-700",
      bgColor: macdValue && macdValue.macd > macdValue.signal ? "bg-green-50" : "bg-red-50",
      description: macdValue && macdValue.macd > macdValue.signal ? "MACD above signal line (bullish)" : "MACD below signal line (bearish)",
    },
    {
      name: "50-Day SMA",
      value: `$${sma50.toFixed(2)}`,
      signal: currentPrice > sma50 ? "Above" : "Below",
      color: currentPrice > sma50 ? "text-green-700" : "text-red-700",
      bgColor: currentPrice > sma50 ? "bg-green-50" : "bg-red-50",
      description: `Price ${currentPrice > sma50 ? "above" : "below"} 50-day MA (${technicals?.signal_summary?.trend_vs_50dma || "unknown"})`,
    },
    {
      name: "200-Day SMA",
      value: `$${sma200.toFixed(2)}`,
      signal: currentPrice > sma200 ? "Above" : "Below",
      color: currentPrice > sma200 ? "text-green-700" : "text-red-700",
      bgColor: currentPrice > sma200 ? "bg-green-50" : "bg-red-50",
      description: `Price ${currentPrice > sma200 ? "above" : "below"} 200-day MA (${technicals?.signal_summary?.trend_vs_200dma || "unknown"})`,
    },
    {
      name: "Bollinger Bands",
      value: bbands ? `$${bbands.middle.toFixed(2)}` : "N/A",
      signal: bbands && currentPrice > bbands.upper ? "Above Upper" : bbands && currentPrice < bbands.lower ? "Below Lower" : "Mid-Range",
      color: bbands && currentPrice > bbands.upper ? "text-red-700" : bbands && currentPrice < bbands.lower ? "text-green-700" : "text-gray-700",
      bgColor: bbands && currentPrice > bbands.upper ? "bg-red-50" : bbands && currentPrice < bbands.lower ? "bg-green-50" : "bg-gray-100",
      description: bbands ? `Middle: $${bbands.middle.toFixed(2)}, Range: $${bbands.lower.toFixed(2)} - $${bbands.upper.toFixed(2)}` : "Bollinger Bands data unavailable",
    },
    {
      name: "Trend Signal",
      value: technicals?.signal_summary?.macd_signal || "Unknown",
      signal: technicals?.signal_summary?.macd_signal === "bullish" ? "Bullish" : "Bearish",
      color: technicals?.signal_summary?.macd_signal === "bullish" ? "text-green-700" : "text-red-700",
      bgColor: technicals?.signal_summary?.macd_signal === "bullish" ? "bg-green-50" : "bg-red-50",
      description: technicals?.signal_summary?.interpretation?.split(".")[0] || "Overall trend analysis",
    },
  ];

  return (
    <div className="space-y-6">
      {/* AI Signal Summary */}
      <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Activity className="text-blue-600 flex-shrink-0 mt-1" size={24} />
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-1">
              Technical Signal Summary
            </h3>
            <p className="text-sm text-gray-700">
              {technicals?.signal_summary?.interpretation || `Loading technical analysis for ${symbol}...`}
            </p>
            <div className="flex gap-4 mt-2 text-xs">
              <span className={`font-medium ${
                technicals?.signal_summary?.rsi_state === "overbought" ? "text-red-600" :
                technicals?.signal_summary?.rsi_state === "oversold" ? "text-green-600" :
                "text-gray-600"
              }`}>
                RSI: {technicals?.signal_summary?.rsi_state || "calculating..."}
              </span>
              <span className={`font-medium ${
                technicals?.signal_summary?.macd_signal === "bullish" ? "text-green-600" :
                technicals?.signal_summary?.macd_signal === "bearish" ? "text-red-600" :
                "text-gray-600"
              }`}>
                MACD: {technicals?.signal_summary?.macd_signal || "calculating..."}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Price Chart */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-900">Price Chart</h3>
          <div className="flex gap-2">
            {(["1M", "3M", "6M", "1Y"] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  timeframe === tf
                    ? "bg-[#191970] text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
        <div ref={chartContainerRef} className="w-full" />
        {priceData && (
          <p className="text-xs text-gray-500 mt-2">
            Showing {priceData.bars?.length || 0} days of price history from Alpha Vantage
          </p>
        )}
      </div>

      {/* Technical Indicators Grid */}
      <div>
        <h3 className="text-base font-semibold text-gray-900 mb-4">
          Technical Indicators
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {indicators.map((indicator) => (
            <div
              key={indicator.name}
              className={`${indicator.bgColor} border border-gray-200 rounded-lg p-4`}
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="text-sm font-semibold text-gray-900">
                  {indicator.name}
                </h4>
                <span
                  className={`px-2 py-0.5 text-xs font-medium ${indicator.color} ${indicator.bgColor} border border-current rounded`}
                >
                  {indicator.signal}
                </span>
              </div>
              <p className={`text-lg font-bold ${indicator.color} mb-1`}>
                {indicator.value}
              </p>
              <p className="text-xs text-gray-600">{indicator.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Key Levels */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="text-base font-semibold text-gray-900 mb-4">Key Levels</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-gray-600 mb-1">Current Price</p>
            <p className="text-lg font-bold text-gray-900">
              ${currentPrice.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 mb-1">52-Week High</p>
            <p className="text-lg font-bold text-gray-900">
              ${week52High.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 mb-1">52-Week Low</p>
            <p className="text-lg font-bold text-gray-900">
              ${week52Low.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-600 mb-1">Price Range</p>
            <p className="text-lg font-bold text-blue-600">
              ${week52Low.toFixed(0)} - ${week52High.toFixed(0)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
