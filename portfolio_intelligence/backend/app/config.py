from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/portfolio_intelligence"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # TradeStation OAuth
    tradestation_client_id: str = ""
    tradestation_client_secret: str = ""
    tradestation_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    tradestation_base_url: str = "https://sim-api.tradestation.com/v3"
    tradestation_token_url: str = "https://signin.tradestation.com/oauth/token"
    tradestation_auth_url: str = "https://signin.tradestation.com/authorize"
    tradestation_audience: str = "https://api.tradestation.com"

    # Security
    secret_key: str = Field(default="change-me-in-production", validation_alias="SECRET_KEY")
    encryption_key: str = ""  # Fernet key for refresh token encryption
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Flask Suite
    suite_url: str = "http://localhost:5000"

    # Testing
    use_mock_tradestation: bool = False  # Set to True to use mock data instead of real API

    # Market Data Provider
    market_data_provider: str = "tradestation"  # "tradestation", "alphavantage", or "mock"
    alphavantage_api_key: str = ""

    # Scheduler
    enable_nightly_updates: bool = True  # Set to False to disable automatic price updates

    # OpenAI / LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-5.2-chat-latest"
    openai_timeout: int = 10  # seconds

    # Company Intelligence Cache TTLs (seconds)
    cache_ttl_quote: int = 300  # 5 min
    cache_ttl_news: int = 900  # 15 min
    cache_ttl_technicals: int = 3600  # 1 hour
    cache_ttl_overview: int = 86400  # 24 hours
    cache_ttl_financials: int = 86400  # 24 hours
    cache_ttl_earnings: int = 86400  # 24 hours
    cache_ttl_insights: int = 1800  # 30 min
    cache_ttl_narrative: int = 86400  # 24 hours

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
