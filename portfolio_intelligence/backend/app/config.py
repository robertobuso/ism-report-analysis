from pydantic_settings import BaseSettings
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
    secret_key: str = "change-me-in-production"
    encryption_key: str = ""  # Fernet key for refresh token encryption
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Flask Suite
    suite_url: str = "http://localhost:5000"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
