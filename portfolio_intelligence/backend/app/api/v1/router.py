from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.portfolios import router as portfolios_router
from app.api.v1.instruments import router as instruments_router
from app.api.v1.analytics import router as analytics_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(portfolios_router)
v1_router.include_router(instruments_router)
v1_router.include_router(analytics_router)
