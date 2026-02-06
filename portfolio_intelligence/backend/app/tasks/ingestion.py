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

    Note: Works with AlphaVantage (API key-based) and Mock providers.
    TradeStation requires OAuth tokens and is not supported for automated jobs.
    """
    async def _run():
        from app.db.database import AsyncSessionLocal
        from app.services.ingestion import PriceIngestionService
        from app.dependencies import get_tradestation_client
        from app.config import get_settings

        settings = get_settings()

        # Check if we're using a provider that supports automated updates
        provider = settings.market_data_provider.lower()
        if provider == "tradestation" and not settings.use_mock_tradestation:
            logger.warning("Nightly updates not supported with real TradeStation (requires OAuth)")
            return {"status": "skipped", "reason": "TradeStation requires user OAuth tokens"}

        async with AsyncSessionLocal() as db:
            service = PriceIngestionService(db, get_tradestation_client())
            symbols = await service.get_active_symbols()

            if not symbols:
                logger.info("No active symbols to update")
                return {"symbols_updated": 0}

            logger.info(f"Starting nightly update for {len(symbols)} symbols using {provider}")

            updated_count = 0
            failed_symbols = []

            # Fetch latest price for each symbol (1 bar = today's close)
            for symbol in symbols:
                try:
                    logger.info(f"Updating {symbol}")
                    # Empty access token is fine for AlphaVantage/Mock
                    count = await service.backfill_symbol("", symbol, bars_back=1)
                    if count > 0:
                        updated_count += 1
                    logger.info(f"Updated {symbol}: {count} bars")
                except Exception as e:
                    logger.error(f"Failed to update {symbol}: {e}")
                    failed_symbols.append(symbol)

            logger.info(
                f"Nightly update complete: {updated_count}/{len(symbols)} symbols updated, "
                f"{len(failed_symbols)} failed"
            )

            return {
                "symbols_updated": updated_count,
                "total_symbols": len(symbols),
                "failed_symbols": failed_symbols,
                "provider": provider,
            }

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
