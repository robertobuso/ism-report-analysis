"""
Configuration Management and Integration Components
==================================================

This module provides configuration management, data structures, and integration
components for the enhanced news analysis system.
"""

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class Article:
    """
    Enhanced article data structure with relevance assessment capabilities.
    """
    title: str
    snippet: str
    link: str
    source: str
    published: str = ""
    source_type: str = "google_search"  # alphavantage_premium, nyt_api, rss_feed, google_search
    full_content: str = ""
    
    # AlphaVantage specific fields
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    relevance_score: Optional[float] = None
    
    # Enhanced fields
    relevance_assessment: Optional[Dict[str, float]] = None
    enhanced_score: Optional[float] = None
    is_company_specific: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert article to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Article':
        """Create article from dictionary."""
        return cls(**data)

class ConfigurationManager:
    """
    Manages configuration for the enhanced news analysis system.
    Supports environment variables, JSON files, and runtime configuration.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "news_analysis_config.json"
        self._load_configuration()
    
    def _load_configuration(self):
        """Load configuration from multiple sources with priority order."""
        
        # Default configuration
        self.config = {
            "relevance_thresholds": {
                "min_relevant_premium_articles_before_cse": 8,
                "min_company_relevance_score": 0.6,
                "min_financial_context_score": 0.3,
                "min_relevant_percentage": 0.4
            },
            "google_cse": {
                "max_articles_before_cse_check": 25,
                "enable_cse_fallback": True,
                "cse_article_limit": 10
            },
            "source_weights": {
                "alphavantage_weight": 2.0,
                "nyt_weight": 1.8,
                "premium_rss_weight": 1.5,
                "google_cse_weight": 1.0
            },
            "article_limits": {
                "target_article_count": 30,
                "min_article_count": 15,
                "max_alphavantage_articles": 150,
                "max_nyt_articles": 100,
                "max_rss_articles": 50
            },
            "performance": {
                "enable_full_text_extraction": False,
                "enable_advanced_nlp": False,
                "parallel_processing": True,
                "request_timeout": 15
            },
            "premium_sources": [
                "bloomberg.com",
                "reuters.com", 
                "wsj.com",
                "ft.com",
                "nytimes.com",
                "barrons.com",
                "cnbc.com",
                "marketwatch.com"
            ],
            "unwanted_sources": [
                "benzinga.com",
                "fool.com",
                "zacks.com",
                "investorplace.com"
            ]
        }
        
        # Override with file configuration if exists
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    file_config = json.load(f)
                    self._merge_config(self.config, file_config)
            except Exception as e:
                print(f"Warning: Could not load config file {self.config_file}: {e}")
        
        # Override with environment variables
        self._load_env_overrides()
    
    def _merge_config(self, base: Dict, override: Dict):
        """Recursively merge configuration dictionaries."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def _load_env_overrides(self):
        """Load configuration overrides from environment variables."""
        env_mappings = {
            "NEWS_MIN_RELEVANT_ARTICLES": ("relevance_thresholds", "min_relevant_premium_articles_before_cse"),
            "NEWS_MIN_COMPANY_RELEVANCE": ("relevance_thresholds", "min_company_relevance_score"),
            "NEWS_MIN_FINANCIAL_CONTEXT": ("relevance_thresholds", "min_financial_context_score"),
            "NEWS_MIN_RELEVANT_PERCENTAGE": ("relevance_thresholds", "min_relevant_percentage"),
            "NEWS_TARGET_ARTICLE_COUNT": ("article_limits", "target_article_count"),
            "NEWS_ENABLE_FULL_TEXT": ("performance", "enable_full_text_extraction"),
            "NEWS_ENABLE_ADVANCED_NLP": ("performance", "enable_advanced_nlp")
        }
        
        for env_var, (section, key) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    # Convert to appropriate type
                    if key.endswith("_score") or key.endswith("_percentage"):
                        converted_value = float(value)
                    elif key.endswith("_count") or key.endswith("_articles"):
                        converted_value = int(value)
                    elif key.startswith("enable_"):
                        converted_value = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        converted_value = value
                    
                    self.config[section][key] = converted_value
                except (ValueError, TypeError):
                    print(f"Warning: Invalid value for {env_var}: {value}")
    
    def get(self, section: str, key: str, default=None):
        """Get configuration value with fallback."""
        return self.config.get(section, {}).get(key, default)
    
    def get_analysis_config(self) -> 'NewsAnalysisConfig':
        """Convert configuration to NewsAnalysisConfig object."""
        from news_utils import NewsAnalysisConfig
        
        return NewsAnalysisConfig(
            MIN_RELEVANT_PREMIUM_ARTICLES_BEFORE_CSE=self.get("relevance_thresholds", "min_relevant_premium_articles_before_cse", 8),
            MIN_COMPANY_RELEVANCE_SCORE=self.get("relevance_thresholds", "min_company_relevance_score", 0.6),
            MIN_FINANCIAL_CONTEXT_SCORE=self.get("relevance_thresholds", "min_financial_context_score", 0.3),
            MAX_ARTICLES_BEFORE_CSE_CHECK=self.get("google_cse", "max_articles_before_cse_check", 25),
            MIN_RELEVANT_PERCENTAGE=self.get("relevance_thresholds", "min_relevant_percentage", 0.4),
            ALPHAVANTAGE_WEIGHT=self.get("source_weights", "alphavantage_weight", 2.0),
            NYT_WEIGHT=self.get("source_weights", "nyt_weight", 1.8),
            PREMIUM_RSS_WEIGHT=self.get("source_weights", "premium_rss_weight", 1.5),
            GOOGLE_CSE_WEIGHT=self.get("source_weights", "google_cse_weight", 1.0),
            TARGET_ARTICLE_COUNT=self.get("article_limits", "target_article_count", 30),
            MIN_ARTICLE_COUNT=self.get("article_limits", "min_article_count", 15),
            ENABLE_FULL_TEXT_EXTRACTION=self.get("performance", "enable_full_text_extraction", False),
            ENABLE_ADVANCED_NLP=self.get("performance", "enable_advanced_nlp", False)
        )
    
    def save_config(self):
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config file: {e}")

class IntegrationHelper:
    """
    Helper class for integrating the enhanced system with existing Flask application.
    """
    
    def __init__(self, config_manager: ConfigurationManager):
        self.config_manager = config_manager
    
    def create_flask_route_replacement(self, app):
        """
        Create a Flask route that replaces the existing news analysis endpoint.
        """
        
        @app.route("/news/summary/enhanced", methods=["POST"])
        def get_enhanced_news_summary():
            """Enhanced news analysis endpoint with dynamic relevance assessment."""
            try:
                from flask import request, render_template
                from enhanced_news_analysis import DynamicSourceOrchestrator
                
                # Parse input
                company = request.form.get("company", "").strip()
                days_back = int(request.form.get("days_back", 7))
                
                if not company:
                    return render_template("news_simple.html", 
                                         error="Please enter a company name or ticker symbol")
                
                # Get configuration
                config = self.config_manager.get_analysis_config()
                
                # Run enhanced analysis
                orchestrator = DynamicSourceOrchestrator(config)
                results = orchestrator.fetch_enhanced_news_with_dynamic_cse(company, days_back)
                
                if not results['success']:
                    return render_template("news_simple.html",
                                         error="No articles found. Try a different company or date range.")
                
                # Prepare template data
                template_data = self._prepare_template_data(results, company, days_back)
                
                return render_template("news_results.html", **template_data)
                
            except Exception as e:
                import traceback
                print(f"Enhanced news analysis error: {e}")
                print(traceback.format_exc())
                return render_template("news_simple.html",
                                     error="Analysis temporarily unavailable. Please try again.")
    
    def _prepare_template_data(self, results: Dict[str, Any], company: str, days_back: int) -> Dict[str, Any]:
        """Prepare data for template rendering."""
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_range = f"{start_date.strftime('%B %d, %Y')} – {end_date.strftime('%B %d, %Y')}"
        
        # Convert markdown summaries to HTML
        from news_utils import create_source_url_mapping, convert_markdown_to_html
        
        source_mapping = create_source_url_mapping(results['articles'])
        summaries = {
            key: [convert_markdown_to_html(bullet, source_mapping) for bullet in bullets]
            for key, bullets in results['summaries'].items()
        }
        
        return {
            'company': results.get('resolved_company_name', company),
            'summaries': summaries,
            'articles': results['articles'][:12],  # Top 12 for display
            'all_articles': results['articles'],
            'date_range': date_range,
            'analysis_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
            'article_count': results['metrics']['total_articles'],
            'articles_analyzed': results['metrics']['total_articles'],
            'articles_displayed': min(12, results['metrics']['total_articles']),
            'analysis_quality': results['metrics']['analysis_quality'],
            'high_quality_sources': results['metrics']['premium_sources_count'],
            'premium_coverage': results['metrics']['premium_coverage'],
            'alphavantage_articles': results['metrics']['alphavantage_articles'],
            'alphavantage_coverage': results['metrics']['alphavantage_coverage'],
            'premium_sources_count': results['metrics']['premium_sources_count'],
            'premium_sources_coverage': results['metrics']['premium_coverage'],
            'nyt_articles': results['metrics']['nyt_articles'],
            'rss_articles': results['metrics']['rss_articles'],
            'source_performance': results['source_performance'],
            # Enhanced fields
            'relevant_articles': results['metrics']['relevant_articles'],
            'relevance_percentage': results['metrics']['relevance_percentage'],
            'google_cse_triggered': results['google_cse_triggered'],
            'enhanced_analysis': True
        }

class MonitoringIntegration:
    """
    Integration with monitoring systems to track the enhanced analysis performance.
    """
    
    def __init__(self):
        self.metrics = {
            'total_requests': 0,
            'google_cse_triggered_count': 0,
            'relevance_improvements': [],
            'response_times': [],
            'companies_analyzed': set()
        }
    
    def log_analysis_request(self, company: str, results: Dict[str, Any]):
        """Log analysis request for monitoring."""
        
        self.metrics['total_requests'] += 1
        self.metrics['companies_analyzed'].add(company.lower())
        self.metrics['response_times'].append(results['metrics']['response_time'])
        
        if results['google_cse_triggered']:
            self.metrics['google_cse_triggered_count'] += 1
        
        # Track relevance improvement
        relevance_percentage = results['metrics']['relevance_percentage']
        self.metrics['relevance_improvements'].append({
            'company': company,
            'relevance_percentage': relevance_percentage,
            'google_cse_triggered': results['google_cse_triggered'],
            'timestamp': datetime.now().isoformat()
        })
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for monitoring dashboard."""
        
        avg_response_time = sum(self.metrics['response_times']) / len(self.metrics['response_times']) if self.metrics['response_times'] else 0
        cse_trigger_rate = self.metrics['google_cse_triggered_count'] / self.metrics['total_requests'] if self.metrics['total_requests'] > 0 else 0
        
        recent_relevance = [r['relevance_percentage'] for r in self.metrics['relevance_improvements'][-50:]]
        avg_relevance = sum(recent_relevance) / len(recent_relevance) if recent_relevance else 0
        
        return {
            'total_requests': self.metrics['total_requests'],
            'unique_companies': len(self.metrics['companies_analyzed']),
            'avg_response_time': round(avg_response_time, 2),
            'google_cse_trigger_rate': round(cse_trigger_rate * 100, 1),
            'avg_relevance_percentage': round(avg_relevance, 1),
            'performance_status': 'healthy' if avg_response_time < 30 and avg_relevance > 50 else 'needs_attention'
        }

def create_example_configuration():
    """Create an example configuration file for reference."""
    
    example_config = {
        "relevance_thresholds": {
            "min_relevant_premium_articles_before_cse": 8,
            "min_company_relevance_score": 0.6,
            "min_financial_context_score": 0.3,
            "min_relevant_percentage": 0.4
        },
        "google_cse": {
            "max_articles_before_cse_check": 25,
            "enable_cse_fallback": True,
            "cse_article_limit": 10
        },
        "source_weights": {
            "alphavantage_weight": 2.0,
            "nyt_weight": 1.8,
            "premium_rss_weight": 1.5,
            "google_cse_weight": 1.0
        },
        "article_limits": {
            "target_article_count": 30,
            "min_article_count": 15,
            "max_alphavantage_articles": 150,
            "max_nyt_articles": 100,
            "max_rss_articles": 50
        },
        "performance": {
            "enable_full_text_extraction": False,
            "enable_advanced_nlp": False,
            "parallel_processing": True,
            "request_timeout": 15
        }
    }
    
    with open("news_analysis_config_example.json", "w") as f:
        json.dump(example_config, f, indent=2)
    
    print("Example configuration created: news_analysis_config_example.json")

# Migration helper for existing systems
class MigrationHelper:
    """
    Helper for migrating from the existing system to the enhanced system.
    """
    
    @staticmethod
    def create_compatibility_wrapper():
        """
        Create a wrapper that maintains compatibility with existing function calls.
        """
        
        def fetch_comprehensive_news_guaranteed_30_enhanced_COMPATIBLE(company: str, days_back: int = 7) -> Dict[str, Any]:
            """
            Compatibility wrapper that provides the same interface as the original function
            but uses the enhanced logic internally.
            """
            
            # Initialize enhanced system
            config_manager = ConfigurationManager()
            config = config_manager.get_analysis_config()

            # Override specific thresholds
            config_manager.config['quality_thresholds']['target'] = 8.5
            config_manager.config['iterative_improvement']['max_iterations'] = 4
            
            from enhanced_news_analysis import DynamicSourceOrchestrator
            orchestrator = DynamicSourceOrchestrator(config)
            
            # Run enhanced analysis
            results = orchestrator.fetch_enhanced_news_with_dynamic_cse(company, days_back)
            
            # Convert to original format for backward compatibility
            return {
                'company': company,
                'articles': results['articles'],
                'summaries': results['summaries'],
                'metrics': {
                    'total_articles': results['metrics']['total_articles'],
                    'alphavantage_articles': results['metrics']['alphavantage_articles'],
                    'nyt_articles': results['metrics']['nyt_articles'],
                    'rss_articles': results['metrics']['rss_articles'],
                    'google_articles': results['metrics']['google_articles'],
                    'premium_sources_count': results['metrics']['premium_sources_count'],
                    'high_quality_sources': results['metrics']['premium_sources_count'],
                    'premium_coverage': results['metrics']['premium_coverage'],
                    'alphavantage_coverage': results['metrics']['alphavantage_coverage'],
                    'analysis_quality': results['metrics']['analysis_quality'],
                    'response_time': results['metrics']['response_time'],
                    'articles_analyzed': results['metrics']['total_articles'],
                    'full_content_articles': results['metrics']['alphavantage_articles'] + results['metrics']['nyt_articles']
                },
                'source_performance': results['source_performance'],
                'success': results['success']
            }
        
        return fetch_comprehensive_news_guaranteed_30_enhanced_COMPATIBLE
    
    @staticmethod
    def replace_existing_function():
        """
        Example of how to replace the existing function in news_utils.py
        """
        replacement_code = '''
# Replace the existing fetch_comprehensive_news_guaranteed_30_enhanced function
# with this enhanced version:

def fetch_comprehensive_news_guaranteed_30_enhanced(company: str, days_back: int = 7) -> Dict[str, Any]:
    """
    ENHANCED version with dynamic relevance assessment and intelligent Google CSE triggering.
    
    This replaces the original function with:
    1. Early relevance assessment for premium source articles
    2. Dynamic Google CSE triggering based on relevance, not just quantity
    3. Improved article selection and scoring
    4. Better performance for both well-known and lesser-known companies
    """
    
    # Import the enhanced system
    from configuration_and_integration import ConfigurationManager, MigrationHelper
    
    # Use compatibility wrapper to maintain existing interface
    enhanced_function = MigrationHelper.create_compatibility_wrapper()
    return enhanced_function(company, days_back)
'''
        
        print("To replace the existing function, add this code to news_utils.py:")
        print(replacement_code)

if __name__ == "__main__":
    # Create example configuration
    create_example_configuration()
    
    # Demonstrate migration
    migration_helper = MigrationHelper()
    migration_helper.replace_existing_function()
    
    print("\nEnhanced system configuration and integration components ready!")
    print("Key features:")
    print("- Configurable relevance thresholds")
    print("- Environment variable support")
    print("- Flask integration helper")
    print("- Monitoring integration")
    print("- Backward compatibility wrapper")