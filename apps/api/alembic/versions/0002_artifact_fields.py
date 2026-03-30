"""add artifact role, format, preview_text, sequence_index and storage consistency

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("role", sa.Text, nullable=True))
    op.add_column("artifacts", sa.Column("format", sa.Text, nullable=True))
    op.add_column("artifacts", sa.Column("preview_text", sa.Text, nullable=True))
    op.add_column("artifacts", sa.Column("sequence_index", sa.Integer, nullable=True))

    op.create_check_constraint(
        "ck_artifacts_storage_consistency",
        "artifacts",
        """
        (storage_kind = 'inline' AND inline_data IS NOT NULL AND blob_path IS NULL)
        OR
        (storage_kind = 'blob' AND blob_path IS NOT NULL AND inline_data IS NULL)
        """,
    )

    op.create_index("idx_artifacts_run_sequence", "artifacts", ["run_id", "sequence_index"])
    op.create_index("idx_artifacts_step_sequence", "artifacts", ["step_id", "sequence_index"])


def downgrade() -> None:
    op.drop_index("idx_artifacts_step_sequence", table_name="artifacts")
    op.drop_index("idx_artifacts_run_sequence", table_name="artifacts")

    op.drop_constraint("ck_artifacts_storage_consistency", "artifacts", type_="check")

    op.drop_column("artifacts", "sequence_index")
    op.drop_column("artifacts", "preview_text")
    op.drop_column("artifacts", "format")
    op.drop_column("artifacts", "role")