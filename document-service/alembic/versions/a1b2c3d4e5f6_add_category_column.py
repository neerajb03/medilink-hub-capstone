"""add_category_column

Revision ID: a1b2c3d4e5f6
Revises: 4dc817aaa1c9
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '4dc817aaa1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('category', sa.Text(), nullable=False, server_default='other'))


def downgrade() -> None:
    op.drop_column('documents', 'category')
