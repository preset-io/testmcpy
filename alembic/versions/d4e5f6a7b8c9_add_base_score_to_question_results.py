"""add base_score to question_results

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-28 00:00:00.000000

Stores the pre-penalty mean of evaluator scores so re-scoring (e.g. toggling a
manual false positive) starts from the true base instead of the already
penalised ``score``, which would double-penalise. NULL on legacy rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("question_results", sa.Column("base_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("question_results", "base_score")
