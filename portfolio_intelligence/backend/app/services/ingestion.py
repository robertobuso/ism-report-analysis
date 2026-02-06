import asyncio
import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.price import PriceDaily

logger = logging.getLogger(__name__)


class PriceIngestionService:
    """Service for ingesting market data from TradeStation."""

    def __init__(self, db: AsyncSession, ts_client):
        """
        Args:
            db: AsyncSession for database operations
            ts_client: TradeStation client (real or mock)
        """
        self.db = db
        self.ts_client = ts_client

    async def _get_or_create_instrument(self, symbol: str) -> Instrument:
        result = await self.db.execute(
            select(Instrument).where(Instrument.symbol == symbol.upper())
        )
        instrument = result.scalar_one_or_none()
        if not instrument:
            instrument = Instrument(symbol=symbol.upper())
            self.db.add(instrument)
            await self.db.flush()
        return instrument

    async def backfill_symbol(
        self, access_token: str, symbol: str, bars_back: int = 1825
    ) -> int:
        """Fetch ~5yr history for a symbol and bulk upsert into prices_daily."""
        instrument = await self._get_or_create_instrument(symbol)

        try:
            raw_bars = await self.ts_client.get_daily_bars(
                access_token, symbol, bars_back=bars_back
            )
        except Exception as e:
            logger.error(f"Failed to fetch bars for {symbol}: {e}")
            return 0

        parsed = self.ts_client.parse_bars(raw_bars)
        if not parsed:
            return 0

        # Bulk upsert using PostgreSQL ON CONFLICT
        rows_upserted = 0
        for bar in parsed:
            stmt = pg_insert(PriceDaily).values(
                instrument_id=instrument.id,
                date=bar["date"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                adj_close=bar["adj_close"],
                volume=bar["volume"],
                source="tradestation",
            ).on_conflict_do_update(
                constraint="uq_prices_instrument_date",
                set_={
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "adj_close": bar["adj_close"],
                    "volume": bar["volume"],
                },
            )
            await self.db.execute(stmt)
            rows_upserted += 1

        await self.db.commit()
        logger.info(f"Upserted {rows_upserted} bars for {symbol}")
        return rows_upserted

    async def update_daily_prices(
        self, access_token: str, symbols: list[str]
    ) -> dict[str, int]:
        """Fetch latest bar for each symbol with rate limiting."""
        results = {}
        for symbol in symbols:
            try:
                count = await self.backfill_symbol(access_token, symbol, bars_back=5)
                results[symbol] = count
            except Exception as e:
                logger.error(f"Failed to update {symbol}: {e}")
                results[symbol] = 0
            # Rate limit protection: 1s delay between symbol requests
            await asyncio.sleep(1.0)
        return results

    async def get_active_symbols(self) -> list[str]:
        """Get all unique symbols currently in any portfolio."""
        from app.models.portfolio import PortfolioPosition
        result = await self.db.execute(
            select(PortfolioPosition.symbol).distinct()
        )
        return [row[0] for row in result.all()]
