import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.v1.router import v1_router
from app.dependencies import get_tradestation_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Portfolio Intelligence API starting up...")

    # Determine market data provider
    provider = settings.market_data_provider.upper()
    auth_mode = "Mock OAuth" if settings.use_mock_tradestation else "TradeStation OAuth"
    logger.info(f"🔐 Authentication: {auth_mode}")
    logger.info(f"📊 Market Data Provider: {provider}")

    client = get_tradestation_client()
    yield
    # Cleanup
    await client.close()
    logger.info("Portfolio Intelligence API shutting down.")


app = FastAPI(
    title="Portfolio Intelligence API",
    description="Persistent portfolio analytics powered by TradeStation market data",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, settings.suite_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 routes
app.include_router(v1_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "portfolio-intelligence"}


@app.post("/admin/trigger-price-update")
async def trigger_price_update():
    """Manually dispatch the nightly price update Celery task."""
    from app.tasks.ingestion import nightly_price_update
    task = nightly_price_update.delay()
    return {"task_id": task.id, "status": "dispatched"}
