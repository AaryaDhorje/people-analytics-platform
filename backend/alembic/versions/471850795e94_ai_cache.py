"""ai_cache — read-through cache for AI responses (phase 6)

One operational table, outside the star schema. It exists because Render restarts the
service on deploy and idles it down, so an in-process cache is empty exactly when a demo
starts, and because the Gemini free-tier quota is the binding constraint on the AI layer.

Unlike the initial migration, this one needs no enum cleanup on the way down: it introduces
no new types, so `drop_table` really does return the database to its prior state.

Revision ID: 471850795e94
Revises: 871a493d0d3e
Create Date: 2026-07-31 18:02:20.490728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '471850795e94'
down_revision: Union[str, Sequence[str], None] = '871a493d0d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ai_cache',
    sa.Column('cache_key', sa.String(length=64), nullable=False),
    sa.Column('feature', sa.String(length=32), nullable=False, comment='ask | narrative | risk_explanation | comments'),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='The response body this key resolves to.'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('hits', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('cache_key'),
    comment='Read-through cache for AI responses, keyed by a hash of the feature, the model and the exact inputs. Safe to TRUNCATE: it rebuilds on demand.'
    )
    op.create_index('ix_ai_cache_feature', 'ai_cache', ['feature'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_cache_feature', table_name='ai_cache')
    op.drop_table('ai_cache')
