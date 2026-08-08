"""add portfolio and decision tables (AIOS-402)

Revision ID: 7af79fa5bca5
Revises: 63b2b0f60bc7
Create Date: 2026-08-08 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '7af79fa5bca5'
down_revision: str | None = '63b2b0f60bc7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table('portfolio_positions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('exchange', sa.String(length=32), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=False),
    sa.Column('current_price', sa.Float(), nullable=False),
    sa.Column('allocation', sa.Float(), nullable=False),
    sa.Column('sector', sa.String(length=128), nullable=False),
    sa.Column('status', sa.Enum('open', 'closed', name='position_status', native_enum=False), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('symbol', 'exchange', name='uq_portfolio_positions_symbol_exchange')
    )
    op.create_table('investment_decisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('decision', sa.Enum('buy', 'hold', 'sell', 'wait', 'no_trade', name='decision_action', native_enum=False), nullable=False),
    sa.Column('reason', sa.String(length=1024), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('risk_score', sa.Float(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('supporting_data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_investment_decisions_symbol_timestamp', 'investment_decisions', ['symbol', 'timestamp'], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index('ix_investment_decisions_symbol_timestamp', table_name='investment_decisions')
    op.drop_table('investment_decisions')
    op.drop_table('portfolio_positions')
