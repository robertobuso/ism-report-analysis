"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { ExternalLink, TrendingUp, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import type { NewsSentimentResponse } from "@/lib/types";

interface NewsTabProps {
  symbol: string;
}

// Custom clickable dot component
const CustomDot = (props: any) => {
  const { cx, cy, payload, selectedDate, onDateClick } = props;
  const isSelected = payload.date === selectedDate;

  return (
    <g>
      {/* Large invisible clickable area - 25px radius for easy clicking */}
      <circle
        cx={cx}
        cy={cy}
        r={25}
        fill="transparent"
        onClick={(e) => {
          e.stopPropagation();
          onDateClick(payload.date);
        }}
        style={{ cursor: "pointer" }}
      />
      {/* Visible dot */}
      <circle
        cx={cx}
        cy={cy}
        r={isSelected ? 7 : 5}
        fill={isSelected ? "#191970" : "#764ba2"}
        stroke="white"
        strokeWidth={2}
        style={{ pointerEvents: "none" }}
      />
    </g>
  );
};

export default function NewsTab({ symbol }: NewsTabProps) {
  const [timeRange, setTimeRange] = useState<string | undefined>(undefined);
  const [limit, setLimit] = useState(20);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const { data: news, isLoading } = useQuery<NewsSentimentResponse>({
    queryKey: ["company-news", symbol, timeRange, limit],
    queryFn: () => api.getCompanyNews(symbol, { time_range: timeRange, limit }),
  });

  // Handle date click
  const handleDateClick = (date: string) => {
    setSelectedDate(date === selectedDate ? null : date);
  };

  // Filter articles by selected topic AND/OR selected date
  const filteredArticles = news?.articles.filter((article) => {
    // Filter by topic if selected
    if (selectedTopic && !article.topics.includes(selectedTopic)) {
      return false;
    }

    // Filter by date if selected
    if (selectedDate) {
      const articleDate = new Date(article.time_published).toISOString().split('T')[0];
      if (articleDate !== selectedDate) {
        return false;
      }
    }

    return true;
  }) || [];

  const getSentimentColor = (label: string) => {
    switch (label.toLowerCase()) {
      case "bullish":
      case "somewhat-bullish":
        return "text-green-700 bg-green-100 border-green-300";
      case "bearish":
      case "somewhat-bearish":
        return "text-red-700 bg-red-100 border-red-300";
      default:
        return "text-gray-700 bg-gray-100 border-gray-300";
    }
  };

  const getSentimentIcon = (label: string) => {
    switch (label.toLowerCase()) {
      case "bullish":
      case "somewhat-bullish":
        return <TrendingUp size={14} className="inline" />;
      case "bearish":
      case "somewhat-bearish":
        return <TrendingDown size={14} className="inline" />;
      default:
        return null;
    }
  };

  const formatTimeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-64 mb-4"></div>
          <div className="h-64 bg-gray-200 rounded mb-6"></div>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!news || news.total_articles === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        No recent news available for {symbol}
      </div>
    );
  }

  // Calculate overall sentiment summary
  const avgSentiment =
    news.articles.reduce((sum, a) => sum + a.ticker_sentiment_score, 0) /
    news.articles.length;
  const overallTrend =
    avgSentiment > 0.15
      ? "bullish"
      : avgSentiment < -0.15
        ? "bearish"
        : "neutral";

  return (
    <div className="space-y-6">
      {/* AI Summary */}
      <div className="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-1">
            {overallTrend === "bullish" ? (
              <TrendingUp className="text-green-600" size={24} />
            ) : overallTrend === "bearish" ? (
              <TrendingDown className="text-red-600" size={24} />
            ) : (
              <div className="w-6 h-6 rounded-full bg-gray-400"></div>
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-1">
              Recent News Sentiment
            </h3>
            <p className="text-sm text-gray-700">
              {overallTrend === "bullish" && (
                <>
                  Recent news coverage for <strong>{symbol}</strong> is{" "}
                  <span className="font-semibold text-green-700">
                    predominantly positive
                  </span>
                  , with {news.total_articles} articles showing an average
                  sentiment score of{" "}
                  <span className="font-semibold">
                    {avgSentiment.toFixed(2)}
                  </span>
                  . Key topics include{" "}
                  {Object.keys(news.topic_distribution)
                    .slice(0, 3)
                    .join(", ")}
                  .
                </>
              )}
              {overallTrend === "bearish" && (
                <>
                  Recent news coverage for <strong>{symbol}</strong> is{" "}
                  <span className="font-semibold text-red-700">
                    predominantly negative
                  </span>
                  , with {news.total_articles} articles showing an average
                  sentiment score of{" "}
                  <span className="font-semibold">
                    {avgSentiment.toFixed(2)}
                  </span>
                  . Key topics include{" "}
                  {Object.keys(news.topic_distribution)
                    .slice(0, 3)
                    .join(", ")}
                  .
                </>
              )}
              {overallTrend === "neutral" && (
                <>
                  Recent news coverage for <strong>{symbol}</strong> shows{" "}
                  <span className="font-semibold text-gray-700">
                    mixed sentiment
                  </span>
                  , with {news.total_articles} articles averaging a neutral
                  score of{" "}
                  <span className="font-semibold">
                    {avgSentiment.toFixed(2)}
                  </span>
                  . Key topics include{" "}
                  {Object.keys(news.topic_distribution)
                    .slice(0, 3)
                    .join(", ")}
                  .
                </>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Sentiment Trend Chart */}
      {news.sentiment_trend.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-base font-semibold text-gray-900">
              Sentiment Trend
              {selectedDate && (
                <span className="ml-2 text-xs font-normal text-gray-500">
                  (showing articles from {new Date(selectedDate).toLocaleDateString()})
                </span>
              )}
            </h3>
            {selectedDate && (
              <button
                onClick={() => setSelectedDate(null)}
                className="text-xs text-[#191970] hover:underline"
              >
                Clear date filter
              </button>
            )}
          </div>
          <p className="text-xs text-gray-500 mb-3">
            💡 Click any dot to see articles from that day
          </p>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={news.sentiment_trend}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => {
                  const date = new Date(value);
                  return `${date.getMonth() + 1}/${date.getDate()}`;
                }}
              />
              <YAxis
                domain={[-1, 1]}
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => value.toFixed(1)}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const data = payload[0].payload;
                  const isSelected = data.date === selectedDate;
                  return (
                    <div className={`border rounded-lg p-3 shadow-lg ${
                      isSelected
                        ? 'bg-[#191970] border-[#191970]'
                        : 'bg-white border-gray-300'
                    }`}>
                      <p className={`text-xs font-semibold ${
                        isSelected ? 'text-white' : 'text-gray-900'
                      }`}>
                        {new Date(data.date).toLocaleDateString()}
                      </p>
                      <p className={`text-xs ${
                        isSelected ? 'text-gray-200' : 'text-gray-700'
                      }`}>
                        Score: {data.score.toFixed(2)}
                      </p>
                      <p className={`text-xs ${
                        isSelected ? 'text-gray-300' : 'text-gray-500'
                      }`}>
                        {data.article_count} articles
                      </p>
                      {isSelected && (
                        <p className="text-xs text-white font-semibold mt-1">
                          ✓ Selected
                        </p>
                      )}
                    </div>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="score"
                stroke="#764ba2"
                strokeWidth={2}
                dot={(props) => (
                  <CustomDot
                    {...props}
                    selectedDate={selectedDate}
                    onDateClick={handleDateClick}
                  />
                )}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Topic Distribution */}
      {Object.keys(news.topic_distribution).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-3">
            Topics Covered
            {selectedTopic && (
              <span className="ml-2 text-xs font-normal text-gray-500">
                (filtering by {selectedTopic})
              </span>
            )}
          </h3>
          <div className="flex flex-wrap gap-2">
            {/* All Topics button */}
            <button
              onClick={() => setSelectedTopic(null)}
              className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                selectedTopic === null
                  ? "text-white bg-[#191970] border-[#191970]"
                  : "text-gray-700 bg-gray-100 border-gray-300 hover:bg-gray-200"
              } border`}
            >
              All ({news.total_articles})
            </button>

            {Object.entries(news.topic_distribution)
              .sort(([, a], [, b]) => b - a)
              .map(([topic, count]) => (
                <button
                  key={topic}
                  onClick={() => setSelectedTopic(topic === selectedTopic ? null : topic)}
                  className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                    selectedTopic === topic
                      ? "text-white bg-[#191970] border-[#191970]"
                      : "text-gray-700 bg-gray-100 border-gray-300 hover:bg-gray-200"
                  } border cursor-pointer`}
                >
                  {topic} ({count})
                </button>
              ))}
          </div>
        </div>
      )}

      {/* News Articles */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Latest Articles ({filteredArticles.length}
              {(selectedTopic || selectedDate) && ` of ${news.total_articles}`})
            </h3>
            {(selectedTopic || selectedDate) && (
              <div className="flex items-center gap-2 mt-1">
                {selectedTopic && (
                  <span className="text-xs text-gray-600">
                    📌 Topic: <span className="font-medium">{selectedTopic}</span>
                  </span>
                )}
                {selectedDate && (
                  <span className="text-xs text-gray-600">
                    📅 Date: <span className="font-medium">{new Date(selectedDate).toLocaleDateString()}</span>
                  </span>
                )}
                <button
                  onClick={() => {
                    setSelectedTopic(null);
                    setSelectedDate(null);
                  }}
                  className="text-xs text-[#191970] hover:underline"
                >
                  Clear all filters
                </button>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="px-3 py-1 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#191970]"
            >
              <option value={10}>Show 10</option>
              <option value={20}>Show 20</option>
              <option value={50}>Show 50</option>
            </select>
          </div>
        </div>

        {filteredArticles.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p className="mb-2">No articles found with current filters</p>
            {(selectedTopic || selectedDate) && (
              <button
                onClick={() => {
                  setSelectedTopic(null);
                  setSelectedDate(null);
                }}
                className="text-sm text-[#191970] hover:underline"
              >
                Clear all filters
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {filteredArticles.map((article, idx) => (
            <div
              key={idx}
              className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow"
            >
              <div className="flex gap-4 p-4">
                {/* Article Image */}
                {article.banner_image && (
                  <div className="flex-shrink-0 w-32 h-24 bg-gray-100 rounded overflow-hidden">
                    <img
                      src={article.banner_image}
                      alt=""
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  </div>
                )}

                {/* Article Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-base font-semibold text-gray-900 hover:text-[#191970] line-clamp-2"
                    >
                      {article.title}
                      <ExternalLink
                        size={14}
                        className="inline ml-1 text-gray-400"
                      />
                    </a>
                    <span
                      className={`flex-shrink-0 px-2 py-1 text-xs font-medium border rounded ${getSentimentColor(article.ticker_sentiment_label)}`}
                    >
                      {getSentimentIcon(article.ticker_sentiment_label)}{" "}
                      {article.ticker_sentiment_label.replace("-", " ")}
                    </span>
                  </div>

                  <p className="text-sm text-gray-600 line-clamp-2 mb-2">
                    {article.summary}
                  </p>

                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span className="font-medium">{article.source}</span>
                    <span>{formatTimeAgo(article.time_published)}</span>
                    <span>
                      Relevance: {(article.ticker_relevance_score * 100).toFixed(0)}%
                    </span>
                  </div>

                  {/* Article Topics */}
                  {article.topics.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {article.topics.slice(0, 4).map((topic, topicIdx) => (
                        <span
                          key={topicIdx}
                          className="px-2 py-0.5 text-xs text-gray-600 bg-gray-50 rounded"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          </div>
        )}
      </div>
    </div>
  );
}
