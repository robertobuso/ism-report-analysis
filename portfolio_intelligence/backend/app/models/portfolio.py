import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    String, DateTime, Integer, Numeric, Text, ForeignKey, Enum, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AllocationType(str, enum.Enum):
    weight = "weight"
    quantity = "quantity"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(10), default="USD")
    allocation_type: Mapped[AllocationType] = mapped_column(
        Enum(AllocationType), nullable=False, server_default="quantity"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="portfolios")
    versions = relationship(
        "PortfolioVersion", back_populates="portfolio",
        cascade="all, delete-orphan", order_by="PortfolioVersion.version_number"
    )

    def __repr__(self) -> str:
        return f"<Portfolio {self.name}>"


class PortfolioVersion(Base):
    __tablename__ = "portfolio_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    portfolio = relationship("Portfolio", back_populates="versions")
    positions = relationship(
        "PortfolioPosition", back_populates="version",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PortfolioVersion {self.portfolio_id} v{self.version_number}>"


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_versions.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    allocation_type: Mapped[AllocationType] = mapped_column(
        Enum(AllocationType), nullable=False
    )
    value: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)

    version = relationship("PortfolioVersion", back_populates="positions")

    def __repr__(self) -> str:
        return f"<Position {self.symbol} {self.allocation_type.value}={self.value}>"
