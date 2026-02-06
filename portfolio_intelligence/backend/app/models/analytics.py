import uuid
from datetime import date, datetime

from sqlalchemy import Date, Numeric, ForeignKey, UniqueConstraint, func, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PortfolioMetricsDaily(Base):
    __tablename__ = "portfolio_metrics_daily"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[float] = mapped_column(Numeric(18, 8))
    return_1d: Mapped[float | None] = mapped_column(Numeric(18, 8))
    return_mtd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    return_ytd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    volatility_30d: Mapped[float | None] = mapped_column(Numeric(18, 8))
    max_drawdown: Mapped[float | None] = mapped_column(Numeric(18, 8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("portfolio_id", "date", name="uq_metrics_portfolio_date"),
    )

    def __repr__(self) -> str:
        return f"<PortfolioMetrics {self.portfolio_id} {self.date}>"
