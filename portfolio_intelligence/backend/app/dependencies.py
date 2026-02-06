import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_async_session
from app.models.user import User
from app.services.tradestation import TradeStationClient
from app.services.mock_tradestation import MockTradeStationClient
from app.services.alphavantage import AlphaVantageAdapter

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

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
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
