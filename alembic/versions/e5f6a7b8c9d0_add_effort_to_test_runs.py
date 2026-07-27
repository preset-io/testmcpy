"""add effort to test_runs

Records the reasoning-effort level a run was executed at (low/medium/high/...),
so the performance leaderboard can treat effort as a grouping dimension and
plot accuracy-vs-cost effort curves. NULL = the provider default (no effort
requested), which is correct for every historical run.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-24 00:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("effort", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_runs", "effort")
