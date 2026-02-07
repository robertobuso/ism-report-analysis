import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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

    # CRITICAL: Verify SECRET_KEY is properly configured
    if settings.secret_key == "change-me-in-production":
        logger.error("🚨 FATAL: SECRET_KEY is not set! Using default value. JWT validation will fail!")
        logger.error("🚨 Set SECRET_KEY environment variable in Railway and redeploy.")
        raise RuntimeError("SECRET_KEY environment variable is not set!")

    logger.info(f"✅ SECRET_KEY is configured (first 10 chars: {settings.secret_key[:10]}...)")

    # Determine market data provider
    provider = settings.market_data_provider.upper()
    auth_mode = "Mock OAuth" if settings.use_mock_tradestation else "TradeStation OAuth"
    logger.info(f"🔐 Authentication: {auth_mode}")
    logger.info(f"📊 Market Data Provider: {provider}")

    # Start APScheduler for nightly price updates
    scheduler = None

    # Schedule nightly price update at 6 PM ET (18:00 US/Eastern)
    # Note: Only works with AlphaVantage or Mock (TradeStation requires user OAuth)
    if settings.enable_nightly_updates:
        if provider in ("ALPHAVANTAGE", "MOCK"):
            from app.tasks.ingestion import nightly_price_update

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                lambda: nightly_price_update.delay(),
                trigger=CronTrigger(hour=18, minute=0, timezone="US/Eastern"),
                id="nightly_price_update",
                name="Nightly Price Update (6 PM ET)",
                replace_existing=True,
            )
            scheduler.start()
            logger.info("⏰ Scheduled nightly price updates at 6 PM ET")
        else:
            logger.warning("⚠️  Nightly price updates disabled (TradeStation requires OAuth)")
    else:
        logger.info("ℹ️  Nightly price updates disabled (ENABLE_NIGHTLY_UPDATES=false)")

    client = get_tradestation_client()

    yield

    # Cleanup
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler shut down")
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
