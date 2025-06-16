"""
Premium News Sources Monitoring and Analytics

This module provides monitoring capabilities for the enhanced news analysis system.
It tracks source performance, API usage, and analysis quality metrics.

Usage:
    from monitoring import NewsAnalyticsTracker
    tracker = NewsAnalyticsTracker()
    tracker.log_analysis_request(company, sources, quality_metrics)
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from collections import defaultdict, deque
import sqlite3
from dataclasses import dataclass, asdict

@dataclass
class AnalysisMetrics:
    """Data class for tracking analysis metrics."""
    timestamp: str
    company: str
    total_articles: int
    alphavantage_articles: int
    nyt_articles: int
    rss_articles: int
    google_articles: int
    premium_sources: int
    analysis_quality: str
    response_time_seconds: float
    api_errors: List[str]
    source_success_rates: Dict[str, float]

class NewsAnalyticsTracker:
    """Track and analyze news system performance."""
    
    def __init__(self, db_path: str = "news_analytics.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._init_database()
        
        # In-memory metrics for real-time monitoring
        self.recent_requests = deque(maxlen=100)  # Last 100 requests
        self.source_performance = defaultdict(list)
        self.api_call_counts = defaultdict(int)
    
    def _init_database(self):
        """Initialize SQLite database for persistent analytics."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create analytics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analysis_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    company TEXT NOT NULL,
                    total_articles INTEGER,
                    alphavantage_articles INTEGER,
                    nyt_articles INTEGER,
                    rss_articles INTEGER,
                    google_articles INTEGER,
                    premium_sources INTEGER,
                    analysis_quality TEXT,
                    response_time_seconds REAL,
                    api_errors TEXT,
                    source_success_rates TEXT
                )
            ''')
            
            # Create API usage tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    api_source TEXT NOT NULL,
                    success BOOLEAN,
                    response_time_ms INTEGER,
                    error_message TEXT,
                    rate_limited BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Create source performance table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    total_calls INTEGER,
                    successful_calls INTEGER,
                    avg_response_time_ms REAL,
                    avg_articles_per_call REAL,
                    error_rate REAL
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("Analytics database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize analytics database: {e}")
    
    def log_analysis_request(self, 
                           company: str,
                           article_counts: Dict[str, int],
                           analysis_quality: str,
                           response_time: float,
                           api_errors: List[str] = None,
                           source_success_rates: Dict[str, float] = None):
        """Log a complete analysis request for monitoring."""
        
        if api_errors is None:
            api_errors = []
        if source_success_rates is None:
            source_success_rates = {}
        
        # Create metrics object
        metrics = AnalysisMetrics(
            timestamp=datetime.now().isoformat(),
            company=company,
            total_articles=article_counts.get('total', 0),
            alphavantage_articles=article_counts.get('alphavantage', 0),
            nyt_articles=article_counts.get('nyt', 0),
            rss_articles=article_counts.get('rss', 0),
            google_articles=article_counts.get('google', 0),
            premium_sources=article_counts.get('premium', 0),
            analysis_quality=analysis_quality,
            response_time_seconds=response_time,
            api_errors=api_errors,
            source_success_rates=source_success_rates
        )
        
        # Store in memory for real-time access
        self.recent_requests.append(metrics)
        
        # Store in database
        self._store_metrics_to_db(metrics)
        
        # Log key metrics
        self.logger.info(
            f"Analysis logged: {company} | "
            f"Quality: {analysis_quality} | "
            f"Articles: {metrics.total_articles} "
            f"(AV:{metrics.alphavantage_articles}, NYT:{metrics.nyt_articles}, RSS:{metrics.rss_articles}) | "
            f"Response: {response_time:.2f}s"
        )
    
    def log_api_call(self, 
                    api_source: str, 
                    success: bool, 
                    response_time_ms: int,
                    error_message: str = None,
                    rate_limited: bool = False):
        """Log individual API call for detailed monitoring."""
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO api_usage 
                (timestamp, api_source, success, response_time_ms, error_message, rate_limited)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                api_source,
                success,
                response_time_ms,
                error_message,
                rate_limited
            ))
            
            conn.commit()
            conn.close()
            
            # Update in-memory counters
            self.api_call_counts[api_source] += 1
            
            if not success:
                self.logger.warning(f"API call failed: {api_source} | Error: {error_message}")
            
        except Exception as e:
            self.logger.error(f"Failed to log API call: {e}")
    
    def _store_metrics_to_db(self, metrics: AnalysisMetrics):
        """Store analysis metrics to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO analysis_metrics 
                (timestamp, company, total_articles, alphavantage_articles, nyt_articles, 
                 rss_articles, google_articles, premium_sources, analysis_quality, 
                 response_time_seconds, api_errors, source_success_rates)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metrics.timestamp,
                metrics.company,
                metrics.total_articles,
                metrics.alphavantage_articles,
                metrics.nyt_articles,
                metrics.rss_articles,
                metrics.google_articles,
                metrics.premium_sources,
                metrics.analysis_quality,
                metrics.response_time_seconds,
                json.dumps(metrics.api_errors),
                json.dumps(metrics.source_success_rates)
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to store metrics to database: {e}")
    
    def get_performance_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get performance summary for the last N days."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Get basic statistics
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_analyses,
                    AVG(total_articles) as avg_articles,
                    AVG(alphavantage_articles) as avg_alphavantage,
                    AVG(nyt_articles) as avg_nyt,
                    AVG(rss_articles) as avg_rss,
                    AVG(response_time_seconds) as avg_response_time,
                    AVG(CAST(premium_sources AS REAL) / CAST(total_articles AS REAL) * 100) as avg_premium_percentage
                FROM analysis_metrics 
                WHERE timestamp > ?
            ''', (cutoff_date,))
            
            stats = cursor.fetchone()
            
            # Get quality distribution
            cursor.execute('''
                SELECT analysis_quality, COUNT(*) 
                FROM analysis_metrics 
                WHERE timestamp > ?
                GROUP BY analysis_quality
            ''', (cutoff_date,))
            
            quality_dist = dict(cursor.fetchall())
            
            # Get API performance
            cursor.execute('''
                SELECT 
                    api_source,
                    COUNT(*) as total_calls,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_calls,
                    AVG(response_time_ms) as avg_response_time,
                    SUM(CASE WHEN rate_limited THEN 1 ELSE 0 END) as rate_limited_calls
                FROM api_usage 
                WHERE timestamp > ?
                GROUP BY api_source
            ''', (cutoff_date,))
            
            api_performance = {}
            for row in cursor.fetchall():
                source, total, success, avg_time, rate_limited = row
                api_performance[source] = {
                    'total_calls': total,
                    'success_rate': (success / total * 100) if total > 0 else 0,
                    'avg_response_time_ms': avg_time,
                    'rate_limited_calls': rate_limited
                }
            
            conn.close()
            
            # Compile summary
            summary = {
                'period_days': days,
                'total_analyses': stats[0] if stats[0] else 0,
                'avg_articles_per_analysis': round(stats[1], 1) if stats[1] else 0,
                'avg_response_time_seconds': round(stats[6], 2) if stats[6] else 0,
                'avg_premium_percentage': round(stats[7], 1) if stats[7] else 0,
                'source_breakdown': {
                    'alphavantage_avg': round(stats[2], 1) if stats[2] else 0,
                    'nyt_avg': round(stats[3], 1) if stats[3] else 0,
                    'rss_avg': round(stats[4], 1) if stats[4] else 0
                },
                'quality_distribution': quality_dist,
                'api_performance': api_performance,
                'generated_at': datetime.now().isoformat()
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Failed to generate performance summary: {e}")
            return {}
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics from in-memory data."""
        if not self.recent_requests:
            return {"status": "no_recent_data"}
        
        recent_count = len(self.recent_requests)
        recent_list = list(self.recent_requests)
        
        # Calculate averages for recent requests
        avg_articles = sum(r.total_articles for r in recent_list) / recent_count
        avg_response_time = sum(r.response_time_seconds for r in recent_list) / recent_count
        
        # Quality distribution
        quality_counts = defaultdict(int)
        for r in recent_list:
            quality_counts[r.analysis_quality] += 1
        
        # Source performance
        source_totals = defaultdict(int)
        for r in recent_list:
            source_totals['alphavantage'] += r.alphavantage_articles
            source_totals['nyt'] += r.nyt_articles
            source_totals['rss'] += r.rss_articles
            source_totals['google'] += r.google_articles
        
        return {
            'recent_requests_count': recent_count,
            'avg_articles': round(avg_articles, 1),
            'avg_response_time': round(avg_response_time, 2),
            'quality_distribution': dict(quality_counts),
            'source_totals': dict(source_totals),
            'api_call_counts': dict(self.api_call_counts),
            'timestamp': datetime.now().isoformat()
        }
    
    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect performance anomalies and potential issues."""
        anomalies = []
        
        try:
            # Check recent performance vs historical
            recent_summary = self.get_performance_summary(days=1)
            historical_summary = self.get_performance_summary(days=30)
            
            if recent_summary and historical_summary:
                # Check for significant drops in article count
                recent_avg = recent_summary.get('avg_articles_per_analysis', 0)
                historical_avg = historical_summary.get('avg_articles_per_analysis', 0)
                
                if historical_avg > 0 and recent_avg < historical_avg * 0.7:
                    anomalies.append({
                        'type': 'low_article_count',
                        'severity': 'medium',
                        'message': f'Recent average articles ({recent_avg:.1f}) significantly below historical average ({historical_avg:.1f})',
                        'recommendation': 'Check API keys and source availability'
                    })
                
                # Check for increased response times
                recent_time = recent_summary.get('avg_response_time_seconds', 0)
                historical_time = historical_summary.get('avg_response_time_seconds', 0)
                
                if historical_time > 0 and recent_time > historical_time * 1.5:
                    anomalies.append({
                        'type': 'slow_response',
                        'severity': 'low',
                        'message': f'Response times increased from {historical_time:.2f}s to {recent_time:.2f}s',
                        'recommendation': 'Monitor API response times and network connectivity'
                    })
                
                # Check API success rates
                for api, perf in recent_summary.get('api_performance', {}).items():
                    if perf.get('success_rate', 100) < 80:
                        anomalies.append({
                            'type': 'api_failures',
                            'severity': 'high',
                            'message': f'{api} API success rate is {perf["success_rate"]:.1f}% (< 80%)',
                            'recommendation': f'Check {api} API key and service status'
                        })
                    
                    if perf.get('rate_limited_calls', 0) > 0:
                        anomalies.append({
                            'type': 'rate_limiting',
                            'severity': 'medium',
                            'message': f'{api} has {perf["rate_limited_calls"]} rate-limited calls',
                            'recommendation': f'Consider upgrading {api} API plan or reducing request frequency'
                        })
            
            # Check in-memory metrics for immediate issues
            recent_metrics = self.get_real_time_metrics()
            
            if recent_metrics.get('recent_requests_count', 0) == 0:
                anomalies.append({
                    'type': 'no_recent_activity',
                    'severity': 'low',
                    'message': 'No recent analysis requests detected',
                    'recommendation': 'Verify application is receiving requests'
                })
            
        except Exception as e:
            self.logger.error(f"Error detecting anomalies: {e}")
            anomalies.append({
                'type': 'monitoring_error',
                'severity': 'medium',
                'message': f'Failed to run anomaly detection: {e}',
                'recommendation': 'Check monitoring system configuration'
            })
        
        return anomalies
    
    def export_metrics(self, days: int = 30, format: str = 'json') -> str:
        """Export metrics for external analysis."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            if format == 'json':
                # Export as JSON
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                
                cursor.execute('''
                    SELECT * FROM analysis_metrics 
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                ''', (cutoff_date,))
                
                columns = [description[0] for description in cursor.description]
                rows = cursor.fetchall()
                
                data = [dict(zip(columns, row)) for row in rows]
                
                export_data = {
                    'export_timestamp': datetime.now().isoformat(),
                    'period_days': days,
                    'total_records': len(data),
                    'metrics': data,
                    'summary': self.get_performance_summary(days)
                }
                
                conn.close()
                return json.dumps(export_data, indent=2)
            
            else:
                raise ValueError(f"Unsupported export format: {format}")
        
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")
            return json.dumps({"error": str(e)})

# Global analytics tracker instance
analytics_tracker = NewsAnalyticsTracker()

def log_analysis_request(*args, **kwargs):
    """Convenience function for logging analysis requests."""
    analytics_tracker.log_analysis_request(*args, **kwargs)

def log_api_call(*args, **kwargs):
    """Convenience function for logging API calls."""
    analytics_tracker.log_api_call(*args, **kwargs)

def get_performance_dashboard() -> Dict[str, Any]:
    """Get comprehensive performance dashboard data."""
    try:
        # Get various time periods
        daily_summary = analytics_tracker.get_performance_summary(days=1)
        weekly_summary = analytics_tracker.get_performance_summary(days=7)
        monthly_summary = analytics_tracker.get_performance_summary(days=30)
        real_time = analytics_tracker.get_real_time_metrics()
        anomalies = analytics_tracker.detect_anomalies()
        
        # Calculate trends
        trends = {}
        if weekly_summary and monthly_summary:
            weekly_avg = weekly_summary.get('avg_articles_per_analysis', 0)
            monthly_avg = monthly_summary.get('avg_articles_per_analysis', 0)
            
            if monthly_avg > 0:
                trends['article_trend'] = ((weekly_avg - monthly_avg) / monthly_avg * 100)
            
            weekly_quality = weekly_summary.get('avg_premium_percentage', 0)
            monthly_quality = monthly_summary.get('avg_premium_percentage', 0)
            
            if monthly_quality > 0:
                trends['quality_trend'] = ((weekly_quality - monthly_quality) / monthly_quality * 100)
        
        return {
            'dashboard_generated': datetime.now().isoformat(),
            'real_time_metrics': real_time,
            'daily_summary': daily_summary,
            'weekly_summary': weekly_summary,
            'monthly_summary': monthly_summary,
            'trends': trends,
            'anomalies': anomalies,
            'health_status': 'healthy' if len(anomalies) == 0 else 'issues_detected'
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'dashboard_generated': datetime.now().isoformat(),
            'health_status': 'error'
        }

# Example usage for integration into app.py:
"""
# Add this to your news analysis route in app.py:

from monitoring import log_analysis_request, log_api_call
import time

@app.route("/news/summary", methods=["POST"])
@login_required
def get_news_summary():
    start_time = time.time()
    
    try:
        company = request.form.get("company", "").strip()
        days_back = int(request.form.get("days_back", 7))
        
        # ... your existing analysis code ...
        
        # Log the analysis request
        article_counts = {
            'total': len(all_articles),
            'alphavantage': alphavantage_count,
            'nyt': nyt_articles,
            'rss': rss_articles,
            'google': google_count,
            'premium': high_quality_sources
        }
        
        response_time = time.time() - start_time
        
        log_analysis_request(
            company=company,
            article_counts=article_counts,
            analysis_quality=analysis_quality,
            response_time=response_time
        )
        
        # ... return your response ...
        
    except Exception as e:
        response_time = time.time() - start_time
        log_analysis_request(
            company=company,
            article_counts={'total': 0},
            analysis_quality='error',
            response_time=response_time,
            api_errors=[str(e)]
        )
        raise

# Add monitoring endpoint:
@app.route("/admin/performance")
@login_required  # Add appropriate admin authentication
def performance_dashboard():
    dashboard_data = get_performance_dashboard()
    return jsonify(dashboard_data)
"""