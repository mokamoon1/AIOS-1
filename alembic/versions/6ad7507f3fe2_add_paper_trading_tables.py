"""add paper trading tables (AIOS-407)

Revision ID: 6ad7507f3fe2
Revises: 7af79fa5bca5
Create Date: 2026-08-08 04:16:51.908767
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '6ad7507f3fe2'
down_revision: str | None = '7af79fa5bca5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration (paper trading tables, AIOS-407)."""
    op.create_table('paper_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.String(length=64), nullable=False),
    sa.Column('broker_id', sa.String(length=64), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('exchange', sa.String(length=32), nullable=False),
    sa.Column('side', sa.Enum('buy', 'sell', name='order_side', native_enum=False), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'filled', 'cancelled', 'rejected', name='order_status', native_enum=False), nullable=False),
    sa.Column('reason', sa.String(length=512), nullable=False),
    sa.Column('decision_ref', sa.String(length=255), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_id')
    )
    op.create_index('ix_paper_orders_symbol_status', 'paper_orders', ['symbol', 'status'], unique=False)
    op.create_index('ix_paper_orders_broker_submitted', 'paper_orders', ['broker_id', 'submitted_at'], unique=False)
    op.create_table('paper_fills',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fill_id', sa.String(length=64), nullable=False),
    sa.Column('order_id', sa.String(length=64), nullable=False),
    sa.Column('broker_id', sa.String(length=64), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('exchange', sa.String(length=32), nullable=False),
    sa.Column('side', sa.Enum('buy', 'sell', name='order_side', native_enum=False), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('realized_pnl', sa.Float(), nullable=False),
    sa.Column('filled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fill_id')
    )
    op.create_index('ix_paper_fills_order_id', 'paper_fills', ['order_id'], unique=False)
    op.create_table('paper_positions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('exchange', sa.String(length=32), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=False),
    sa.Column('current_price', sa.Float(), nullable=False),
    sa.Column('market_value', sa.Float(), nullable=False),
    sa.Column('unrealized_pnl', sa.Float(), nullable=False),
    sa.Column('realized_pnl', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('symbol', 'exchange', name='uq_paper_positions_symbol_exchange')
    )
    op.create_table('broker_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('broker_id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=64), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('cash', sa.Float(), nullable=False),
    sa.Column('initial_cash', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('broker_id')
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table('broker_accounts')
    op.drop_table('paper_positions')
    op.drop_index('ix_paper_fills_order_id', table_name='paper_fills')
    op.drop_table('paper_fills')
    op.drop_index('ix_paper_orders_broker_submitted', table_name='paper_orders')
    op.drop_index('ix_paper_orders_symbol_status', table_name='paper_orders')
    op.drop_table('paper_orders')
