"""add user report fields to validation record

Revision ID: bf1b87f8650b
Revises: 473b2a163fbf
Create Date: 2025-08-20 10:43:43.328319

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf1b87f8650b'
down_revision: Union[str, Sequence[str], None] = '473b2a163fbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add user report fields to validation_record table
    op.add_column('validation_record', sa.Column('user_report_link', sa.String(2000), nullable=True))
    op.add_column('validation_record', sa.Column('user_report_text', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove user report fields from validation_record table
    op.drop_column('validation_record', 'user_report_text')
    op.drop_column('validation_record', 'user_report_link')
