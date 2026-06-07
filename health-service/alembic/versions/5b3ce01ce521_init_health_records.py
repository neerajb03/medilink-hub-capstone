"""init_health_records

Revision ID: 5b3ce01ce521
Revises: 
Create Date: 2026-06-08 02:52:27.933870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b3ce01ce521'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # rename records to health_records
    op.rename_table('records', 'health_records')
    # rename user_id to patient_id
    op.alter_column('health_records', 'user_id', new_column_name='patient_id')
    op.create_index(op.f('ix_health_records_patient_id'), 'health_records', ['patient_id'], unique=False)
    
    # add columns
    op.add_column('health_records', sa.Column('doctor_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_health_records_doctor_id'), 'health_records', ['doctor_id'], unique=False)
    
    op.add_column('health_records', sa.Column('appointment_id', sa.UUID(), nullable=True))
    op.add_column('health_records', sa.Column('title', sa.Text(), nullable=True))
    op.add_column('health_records', sa.Column('diagnosis', sa.Text(), nullable=True))
    op.add_column('health_records', sa.Column('prescription_text', sa.Text(), nullable=True))
    op.add_column('health_records', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('health_records', sa.Column('created_by_user_id', sa.UUID(), nullable=True))
    op.add_column('health_records', sa.Column('created_by_role', sa.Text(), nullable=True))
    op.add_column('health_records', sa.Column('is_deleted', sa.Boolean(), server_default='false'))
    op.create_index(op.f('ix_health_records_is_deleted'), 'health_records', ['is_deleted'], unique=False)
    
    # partial index
    op.create_index('uniq_health_record_per_appointment', 'health_records', ['appointment_id'], unique=True, postgresql_where=sa.text('appointment_id IS NOT NULL'))

def downgrade() -> None:
    """Downgrade schema."""
    pass
