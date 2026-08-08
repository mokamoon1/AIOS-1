"""add analysis_results table (AIOS-402)

Revision ID: 63b2b0f60bc7
Revises: 6342d9aafe6f
Create Date: 2026-08-08 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '63b2b0f60bc7'
down_revision: str | None = '6342d9aafe6f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table('analysis_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('analysis_type', sa.String(length=32), nullable=False),
    sa.Column('timeframe', sa.Enum('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo', name='timeframe', native_enum=False), nullable=False),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('result', sa.String(length=64), nullable=True),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('symbol', 'analysis_type', 'timeframe', 'analyzed_at', name='uq_analysis_results_symbol_type_timeframe_analyzed_at')
    )
    op.create_index('ix_analysis_results_symbol_timeframe', 'analysis_results', ['symbol', 'timeframe'], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index('ix_analysis_results_symbol_timeframe', table_name='analysis_results')
    op.drop_table('analysis_results')
