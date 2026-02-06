"""add_allocation_type_to_portfolio

Revision ID: 4f1d797939a2
Revises: d60f5feef542
Create Date: 2026-02-06 17:13:15.568582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f1d797939a2'
down_revision: Union[str, None] = 'd60f5feef542'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add allocation_type column to portfolios table
    op.execute("""
        ALTER TABLE portfolios
        ADD COLUMN allocation_type VARCHAR(8) NOT NULL DEFAULT 'quantity'
    """)

    # Migrate existing data: copy allocation_type from first position of each portfolio
    op.execute("""
        UPDATE portfolios p
        SET allocation_type = (
            SELECT DISTINCT pp.allocation_type
            FROM portfolio_positions pp
            JOIN portfolio_versions pv ON pv.id = pp.portfolio_version_id
            WHERE pv.portfolio_id = p.id
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM portfolio_versions pv
            WHERE pv.portfolio_id = p.id
        )
    """)


def downgrade() -> None:
    op.drop_column('portfolios', 'allocation_type')
