import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.schemas.user import UserRead, TokenResponse
from app.services.tradestation import tradestation_client
from app.services.token_manager import token_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_jwt(user_id: str) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.jwt_expiration_minutes * 60
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


@router.get("/login")
async def login():
    """Redirect to TradeStation OAuth consent page."""
    state = str(uuid.uuid4())
    auth_url = tradestation_client.build_auth_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Exchange authorization code for tokens, create/update user, return JWT."""
    settings = get_settings()

    try:
        token_data = await tradestation_client.exchange_code(code)
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 1200)

    # Get user profile from TradeStation
    try:
        profile = await tradestation_client.get_user_profile(access_token)
        ts_user_id = str(profile.get("Accounts", [{}])[0].get("AccountID", ""))
        email = profile.get("email", f"{ts_user_id}@tradestation.user")
    except Exception:
        ts_user_id = ""
        email = f"user-{uuid.uuid4().hex[:8]}@tradestation.user"

    # Upsert user
    result = await db.execute(
        select(User).where(User.tradestation_user_id == ts_user_id) if ts_user_id
        else select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            tradestation_user_id=ts_user_id or None,
        )
        db.add(user)

    # Encrypt and store refresh token
    if refresh_token:
        user.encrypted_refresh_token = token_manager.encrypt_token(refresh_token)

    await db.commit()
    await db.refresh(user)

    # Cache access token
    tradestation_client.cache_access_token(str(user.id), access_token, expires_in)

    # Create JWT
    jwt_token, jwt_expires_in = _create_jwt(str(user.id))

    # Redirect to frontend with token
    redirect_url = f"{settings.frontend_url}/auth/callback?token={jwt_token}&expires_in={jwt_expires_in}"
    return RedirectResponse(url=redirect_url)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Refresh the TradeStation access token and return a new JWT."""
    if not user.encrypted_refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token stored")

    refresh_token = token_manager.decrypt_token(user.encrypted_refresh_token)

    try:
        token_data = await tradestation_client.refresh_access_token(refresh_token)
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Failed to refresh token")

    # Update stored refresh token if rotated
    new_refresh = token_data.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        user.encrypted_refresh_token = token_manager.encrypt_token(new_refresh)
        await db.commit()

    # Cache new access token
    tradestation_client.cache_access_token(
        str(user.id), token_data["access_token"], token_data.get("expires_in", 1200)
    )

    jwt_token, jwt_expires_in = _create_jwt(str(user.id))
    return TokenResponse(access_token=jwt_token, expires_in=jwt_expires_in)


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(get_current_user)]):
    """Return the current authenticated user profile."""
    return user
