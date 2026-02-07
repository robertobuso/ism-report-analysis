import uuid
import logging
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_async_session
from app.models.user import User
from app.services.tradestation import TradeStationClient
from app.services.mock_tradestation import MockTradeStationClient
from app.services.alphavantage import AlphaVantageAdapter, AlphaVantageClient
from app.services.redis_cache import RedisCacheService
from app.services.llm import LLMService

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_db() -> AsyncSession:
    async for session in get_async_session():
        yield session


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Decode JWT and return the authenticated user."""
    settings = get_settings()
    token = credentials.credentials

    logger.info(f"🔐 Attempting JWT validation (token length: {len(token)})")
    logger.info(f"🔑 SECRET_KEY configured: {settings.secret_key[:10]}... (showing first 10 chars)")
    logger.info(f"🔧 Algorithm: {settings.jwt_algorithm}")

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        logger.info(f"✅ JWT decoded successfully. Payload keys: {list(payload.keys())}")

        # Check if this is a Flask-issued token (has email claim)
        email: str | None = payload.get("email")
        if email:
            logger.info(f"📧 Flask-issued token detected for email: {email}")
            # Flask-issued JWT - look up or create user by email
            try:
                # Look up user by email (Google OAuth users don't have tradestation_user_id)
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one_or_none()

                if user is None:
                    logger.info(f"👤 User not found, creating new user for: {email}")
                    # Create new user from Google OAuth email
                    # Note: tradestation_user_id is None for Google OAuth users
                    user = User(
                        email=email,
                        tradestation_user_id=None,
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    logger.info(f"✅ Created new user with ID: {user.id}")
                else:
                    logger.info(f"✅ Found existing user with ID: {user.id}")

                return user
            except Exception as db_error:
                logger.error(f"❌ Database error during user lookup/creation: {db_error}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database error: {str(db_error)}",
                )

        # Otherwise, check for TradeStation-issued token (has sub claim)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            logger.error(f"❌ Token missing both 'email' and 'sub' claims")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing email or subject",
            )

        logger.info(f"🔷 TradeStation-issued token detected for user_id: {user_id}")
    except JWTError as e:
        logger.error(f"❌ JWT decode failed: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_tradestation_client() -> TradeStationClient | MockTradeStationClient | AlphaVantageAdapter:
    """
    Factory function for market data client.

    Returns appropriate client based on configuration:
    - MARKET_DATA_PROVIDER="mock" → MockTradeStationClient
    - MARKET_DATA_PROVIDER="alphavantage" → AlphaVantageAdapter
    - MARKET_DATA_PROVIDER="tradestation" → TradeStationClient (default)

    Note: MARKET_DATA_PROVIDER takes precedence over USE_MOCK_TRADESTATION.
    This allows mock OAuth with real market data from AlphaVantage.
    """
    settings = get_settings()

    # New provider-based selection (takes precedence)
    provider = settings.market_data_provider.lower()

    if provider == "mock":
        return MockTradeStationClient()
    elif provider == "alphavantage":
        return AlphaVantageAdapter()
    elif provider == "tradestation":
        return TradeStationClient()
    else:
        # Fallback to legacy behavior if provider is unrecognized
        if settings.use_mock_tradestation:
            return MockTradeStationClient()
        return TradeStationClient()


def get_auth_client() -> TradeStationClient | MockTradeStationClient:
    """
    Factory function for OAuth/authentication client.

    ALWAYS returns TradeStation or Mock, regardless of MARKET_DATA_PROVIDER.
    This is because authentication is always done via TradeStation OAuth,
    even if market data comes from AlphaVantage or other providers.

    Returns:
    - USE_MOCK_TRADESTATION=true → MockTradeStationClient
    - Otherwise → TradeStationClient
    """
    settings = get_settings()

    if settings.use_mock_tradestation:
        return MockTradeStationClient()
    else:
        return TradeStationClient()


async def get_redis(request: Request) -> redis.Redis:
    """
    Get Redis client from application state.

    The Redis client is initialized in the lifespan context manager.
    """
    return request.app.state.redis


def get_llm_service() -> LLMService:
    """
    Get LLM service for AI-powered insights.

    Returns:
        LLMService configured with settings from environment
    """
    settings = get_settings()
    return LLMService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout=settings.openai_timeout
    )


def get_alphavantage_client() -> AlphaVantageClient:
    """
    Get AlphaVantage client for Company Intelligence.

    Returns:
        AlphaVantageClient configured with API key from settings
    """
    settings = get_settings()
    return AlphaVantageClient(api_key=settings.alphavantage_api_key)


async def get_redis_cache_service(
    redis_client: Annotated[redis.Redis, Depends(get_redis)]
) -> RedisCacheService:
    """
    Get Redis cache service.

    Args:
        redis_client: Redis client from application state

    Returns:
        RedisCacheService instance
    """
    return RedisCacheService(redis_client)
