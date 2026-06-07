"""init_documents

Revision ID: 4dc817aaa1c9
Revises: 
Create Date: 2026-06-08 02:55:07.902918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4dc817aaa1c9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # rename user_id to patient_id
    op.alter_column('documents', 'user_id', new_column_name='patient_id')
    op.create_index(op.f('ix_documents_patient_id'), 'documents', ['patient_id'], unique=False)
    
    # add columns
    op.add_column('documents', sa.Column('record_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_documents_record_id'), 'documents', ['record_id'], unique=False)
    
    op.add_column('documents', sa.Column('uploaded_by', sa.Text(), nullable=True))
    # If the table has data, we need a default for NOT NULL fields, or we make them True and later alter. 
    # Since we are doing a simple migration script, we'll keep nullable=True initially to be safe against existing data.
    op.add_column('documents', sa.Column('file_type', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('status', sa.Text(), server_default='PENDING'))
    op.add_column('documents', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('documents', sa.Column('created_by_user_id', sa.UUID(), nullable=True))
    op.add_column('documents', sa.Column('created_by_role', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('is_deleted', sa.Boolean(), server_default='false'))
    op.create_index(op.f('ix_documents_is_deleted'), 'documents', ['is_deleted'], unique=False)

def downgrade() -> None:
    """Downgrade schema."""
    pass
