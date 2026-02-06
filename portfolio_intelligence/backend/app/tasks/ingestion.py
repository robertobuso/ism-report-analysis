import asyncio
import logging

from app.worker import celery_app
from app.config import get_settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async code in a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="tasks.nightly_price_update",
    max_retries=3,
    default_retry_delay=60,
)
def nightly_price_update(self):
    """Nightly job: update prices for all active symbols and recompute metrics.

    Runs daily at 6 PM ET. Dispatched by APScheduler in FastAPI lifespan.
    """
    async def _run():
        from app.db.database import AsyncSessionLocal
        from app.services.ingestion import PriceIngestionService

        async with AsyncSessionLocal() as db:
            service = PriceIngestionService(db)
            symbols = await service.get_active_symbols()
            if not symbols:
                logger.info("No active symbols to update")
                return {"symbols_updated": 0}

            # For nightly jobs, we need a service account token or cached token
            # In production, this would use a system-level refresh token
            logger.info(f"Updating prices for {len(symbols)} symbols")

            # TODO: Implement system-level token refresh for nightly jobs
            # For now, this task requires manual trigger with a valid access token
            return {"symbols": symbols, "status": "requires_token"}

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error(f"Nightly price update failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="tasks.backfill_symbol",
    max_retries=3,
    default_retry_delay=30,
)
def backfill_symbol(self, symbol: str, access_token: str, bars_back: int = 1825):
    """Backfill historical prices for a symbol. Triggered when added to portfolio."""

    async def _run():
        from app.db.database import AsyncSessionLocal
        from app.services.ingestion import PriceIngestionService

        async with AsyncSessionLocal() as db:
            service = PriceIngestionService(db)
            count = await service.backfill_symbol(access_token, symbol, bars_back)
            return {"symbol": symbol, "bars_ingested": count}

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error(f"Backfill for {symbol} failed: {exc}")
        raise self.retry(exc=exc)
