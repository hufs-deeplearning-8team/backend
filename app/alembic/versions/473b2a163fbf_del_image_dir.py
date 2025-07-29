"""del : image dir

Revision ID: 473b2a163fbf
Revises: 1b4252a86b93
Create Date: 2025-07-30 02:12:32.949465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '473b2a163fbf'
down_revision: Union[str, Sequence[str], None] = '1b4252a86b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
