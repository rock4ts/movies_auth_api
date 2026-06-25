"""login_history_partition

Revision ID: 95d6f46d7543
Revises: 717fefd51c65
Create Date: 2026-06-21 17:55:26.346606

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "95d6f46d7543"
down_revision: Union[str, None] = "717fefd51c65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
    SELECT partman.create_parent(
        p_parent_table := 'public.login_history',
        p_control := 'logged_in_at',
        p_type := 'range',
        p_interval := '1 month',
        p_premake := 3
    )
    """
    )


def downgrade() -> None:
    pass
