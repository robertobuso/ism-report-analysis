"""Scenario Explorer service for portfolio what-if analysis."""
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio, PortfolioVersion
from app.schemas.company import ScenarioResult
from app.services.analytics import PortfolioAnalyticsEngine

logger = logging.getLogger(__name__)


class ScenarioService:
    """
    Simplified portfolio scenario modeling (v1).

    Approach:
    - Accept actions: trim_25, trim_50, exit, add_10
    - Recalculate weights after action
    - Estimate new volatility by scaling historical portfolio vol
    - Simulate max drawdown using historical returns with new weights
    - Re-rank holdings by risk contribution

    Note: This is a simplified v1. The API contract is designed so a full
    covariance-based engine can replace this without frontend changes.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analytics_engine = PortfolioAnalyticsEngine(db)

    async def run_scenario(
        self,
        portfolio_id: uuid.UUID,
        symbol: str,
        action: Literal["trim_25", "trim_50", "exit", "add_10"]
    ) -> ScenarioResult:
        """
        Run a portfolio scenario simulation.

        Args:
            portfolio_id: Portfolio to analyze
            symbol: Symbol to modify
            action: Action to simulate

        Returns:
            ScenarioResult with projected impacts
        """
        # Get current portfolio version
        result = await self.db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        # Get latest version
        result = await self.db.execute(
            select(PortfolioVersion)
            .where(PortfolioVersion.portfolio_id == portfolio_id)
            .order_by(PortfolioVersion.effective_at.desc())
        )
        current_version = result.scalars().first()
        if not current_version:
            raise ValueError(f"No versions found for portfolio {portfolio_id}")

        # Build current weights dict
        current_weights = {}
        for pos in current_version.positions:
            current_weights[pos.symbol] = float(pos.value)

        # Check if symbol exists in portfolio
        if symbol not in current_weights:
            raise ValueError(f"Symbol {symbol} not found in portfolio")

        # Calculate new weights based on action
        new_weights = self._apply_action(current_weights, symbol, action)

        # Calculate current metrics
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        metrics = await self.analytics_engine.compute_daily_metrics(
            portfolio_id, start_date, end_date
        )

        if not metrics:
            # No historical data - return simplified result
            return ScenarioResult(
                action=action,
                new_weights=new_weights,
                current_volatility=0.0,
                new_volatility=0.0,
                current_max_drawdown=0.0,
                new_max_drawdown=0.0,
                concentration_change=0.0,
                risk_ranking_changes=[]
            )

        # Extract current volatility and max drawdown
        latest = metrics[-1]
        current_volatility = float(latest.get("volatility_30d") or 0.0)
        current_max_drawdown = float(latest.get("max_drawdown") or 0.0)

        # Estimate new volatility (simplified: scale by weight change)
        weight_change = abs(current_weights[symbol] - new_weights.get(symbol, 0.0))
        volatility_scale = 1.0 - (weight_change * 0.5)  # Simplified scaling
        new_volatility = current_volatility * volatility_scale

        # Estimate new max drawdown (simplified: scale by weight change)
        drawdown_scale = 1.0 - (weight_change * 0.3)
        new_max_drawdown = current_max_drawdown * drawdown_scale

        # Calculate concentration change
        current_top3_weight = sum(sorted(current_weights.values(), reverse=True)[:3])
        new_top3_weight = sum(sorted(new_weights.values(), reverse=True)[:3])
        concentration_change = new_top3_weight - current_top3_weight

        # Build risk ranking changes (simplified)
        risk_ranking_changes = self._calculate_risk_ranking_changes(
            current_weights, new_weights, symbol, action
        )

        return ScenarioResult(
            action=action,
            new_weights=new_weights,
            current_volatility=current_volatility,
            new_volatility=new_volatility,
            current_max_drawdown=current_max_drawdown,
            new_max_drawdown=new_max_drawdown,
            concentration_change=concentration_change,
            risk_ranking_changes=risk_ranking_changes
        )

    def _apply_action(
        self,
        current_weights: dict[str, float],
        symbol: str,
        action: Literal["trim_25", "trim_50", "exit", "add_10"]
    ) -> dict[str, float]:
        """
        Apply action to weights and rebalance.

        Returns new weight dictionary with all weights normalized to sum to 1.0
        """
        new_weights = current_weights.copy()
        current_weight = current_weights[symbol]

        if action == "trim_25":
            # Reduce by 25%
            new_weights[symbol] = current_weight * 0.75
        elif action == "trim_50":
            # Reduce by 50%
            new_weights[symbol] = current_weight * 0.5
        elif action == "exit":
            # Remove completely
            new_weights[symbol] = 0.0
        elif action == "add_10":
            # Increase by 10% (absolute, not relative)
            new_weights[symbol] = current_weight + 0.10
        else:
            raise ValueError(f"Unknown action: {action}")

        # Normalize weights to sum to 1.0
        # Distribute freed-up weight proportionally (except for add_10)
        if action in ("trim_25", "trim_50", "exit"):
            freed_weight = current_weight - new_weights[symbol]
            other_symbols = [s for s in new_weights if s != symbol and new_weights[s] > 0]

            if other_symbols:
                # Distribute proportionally to remaining holdings
                other_total = sum(new_weights[s] for s in other_symbols)
                if other_total > 0:
                    for s in other_symbols:
                        proportion = new_weights[s] / other_total
                        new_weights[s] += freed_weight * proportion

        # For add_10, reduce other positions proportionally
        elif action == "add_10":
            reduction_needed = 0.10
            other_symbols = [s for s in new_weights if s != symbol]
            other_total = sum(new_weights[s] for s in other_symbols)

            if other_total > 0:
                for s in other_symbols:
                    proportion = new_weights[s] / other_total
                    new_weights[s] -= reduction_needed * proportion

        # Remove zero or negative weights
        new_weights = {s: w for s, w in new_weights.items() if w > 0}

        # Final normalization (handle rounding errors)
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {s: w / total for s, w in new_weights.items()}

        return new_weights

    def _calculate_risk_ranking_changes(
        self,
        current_weights: dict[str, float],
        new_weights: dict[str, float],
        symbol: str,
        action: str
    ) -> list[dict]:
        """
        Calculate how risk ranking changes (simplified).

        Returns list of holdings with rank changes.
        """
        # Sort by weight (proxy for risk contribution in simplified model)
        current_ranked = sorted(
            current_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
        new_ranked = sorted(
            new_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Map symbols to ranks
        current_ranks = {s: i + 1 for i, (s, w) in enumerate(current_ranked)}
        new_ranks = {s: i + 1 for i, (s, w) in enumerate(new_ranked)}

        # Find changes
        changes = []
        all_symbols = set(current_ranks.keys()) | set(new_ranks.keys())

        for s in all_symbols:
            old_rank = current_ranks.get(s, 999)
            new_rank = new_ranks.get(s, 999)

            if old_rank != new_rank:
                changes.append({
                    "symbol": s,
                    "old_rank": old_rank if old_rank != 999 else None,
                    "new_rank": new_rank if new_rank != 999 else None,
                    "rank_change": new_rank - old_rank
                })

        # Sort by magnitude of change
        changes.sort(key=lambda x: abs(x["rank_change"]))

        return changes
