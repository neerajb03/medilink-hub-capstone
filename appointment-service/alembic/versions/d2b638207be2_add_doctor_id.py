"""add_doctor_id

Revision ID: d2b638207be2
Revises: 
Create Date: 2026-06-08 02:46:35.985840

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2b638207be2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add updated_at and is_deleted
    op.add_column('appointments', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('appointments', sa.Column('is_deleted', sa.Boolean(), server_default='false'))
    
    # Rename user_id to patient_id
    op.alter_column('appointments', 'user_id', new_column_name='patient_id')
    op.create_index(op.f('ix_appointments_patient_id'), 'appointments', ['patient_id'], unique=False)
    op.create_index(op.f('ix_appointments_doctor_id'), 'appointments', ['doctor_id'], unique=False)
    
    # Make doctor_id NOT NULL. If there are existing rows with NULL, this will fail.
    # In a real environment, we would backfill data first. For this phase, we apply it.
    op.alter_column('appointments', 'doctor_id', existing_type=sa.UUID(), nullable=False)

def downgrade() -> None:
    """Downgrade schema."""
    pass
