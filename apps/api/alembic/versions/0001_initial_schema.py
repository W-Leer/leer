"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # --- runs ---
    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.Text),
        sa.Column("workflow_name", sa.Text, nullable=False),
        sa.Column("trigger_type", sa.Text, nullable=False, server_default="manual"),
        sa.Column("source", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("parent_run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("root_run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("input_summary", JSONB),
        sa.Column("output_summary", JSONB),
        sa.Column("error_summary", JSONB),
        sa.Column("model_provider", sa.Text),
        sa.Column("model_name", sa.Text),
        sa.Column("total_steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens_input", sa.Integer),
        sa.Column("total_tokens_output", sa.Integer),
        sa.Column("total_cost_usd", sa.Numeric(12, 6)),
        sa.Column("total_duration_ms", sa.Integer),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
    )

    # --- steps ---
    op.create_table(
        "steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_step_id", UUID(as_uuid=True), sa.ForeignKey("steps.id", ondelete="SET NULL")),
        sa.Column("sequence_index", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("step_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("input_summary", JSONB),
        sa.Column("output_summary", JSONB),
        sa.Column("error_summary", JSONB),
        sa.Column("input_artifact_id", UUID(as_uuid=True)),
        sa.Column("output_artifact_id", UUID(as_uuid=True)),
        sa.Column("config_artifact_id", UUID(as_uuid=True)),
        sa.Column("checkpoint_key", sa.Text),
        sa.Column("is_replayable", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("model_provider", sa.Text),
        sa.Column("model_name", sa.Text),
        sa.Column("token_input", sa.Integer),
        sa.Column("token_output", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(12, 6)),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "step_type IN ('llm', 'tool', 'code', 'router', 'human', 'memory', 'system')",
            name="ck_steps_step_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'failed', 'skipped', 'cancelled')",
            name="ck_steps_status",
        ),
    )

    # --- events ---
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", UUID(as_uuid=True), sa.ForeignKey("steps.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("sequence_index", sa.Integer, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    # --- artifacts ---
    op.create_table(
        "artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE")),
        sa.Column("step_id", UUID(as_uuid=True), sa.ForeignKey("steps.id", ondelete="CASCADE")),
        sa.Column("artifact_type", sa.Text, nullable=False),
        sa.Column("storage_kind", sa.Text, nullable=False),
        sa.Column("mime_type", sa.Text),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("inline_data", JSONB),
        sa.Column("blob_path", sa.Text),
        sa.Column("sha256", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "storage_kind IN ('inline', 'blob')",
            name="ck_artifacts_storage_kind",
        ),
    )

    # --- replays ---
    op.create_table(
        "replays",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_step_id", UUID(as_uuid=True), sa.ForeignKey("steps.id", ondelete="SET NULL")),
        sa.Column("replay_run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("replay_mode", sa.Text, nullable=False),
        sa.Column("override_config_artifact_id", UUID(as_uuid=True)),
        sa.Column("reason", sa.Text),
        sa.Column("created_by", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "replay_mode IN ('full', 'from_step', 'step_only', 'fork')",
            name="ck_replays_replay_mode",
        ),
    )

    # --- indexes (from db-schema.md) ---
    op.create_index("idx_runs_project_created_at", "runs", ["project_id", sa.text("created_at DESC")])
    op.create_index("idx_runs_root_run_id", "runs", ["root_run_id"])
    op.create_index("idx_runs_parent_run_id", "runs", ["parent_run_id"])

    op.create_index("idx_steps_run_sequence", "steps", ["run_id", "sequence_index"])
    op.create_index("idx_steps_parent_step_id", "steps", ["parent_step_id"])

    op.create_index("idx_events_run_sequence", "events", ["run_id", "sequence_index"])
    op.create_index("idx_events_step_sequence", "events", ["step_id", "sequence_index"])

    op.create_index("idx_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("idx_artifacts_step_id", "artifacts", ["step_id"])

    op.create_index("idx_replays_source_run_id", "replays", ["source_run_id"])


def downgrade() -> None:
    op.drop_table("replays")
    op.drop_table("artifacts")
    op.drop_table("events")
    op.drop_table("steps")
    op.drop_table("runs")
    op.drop_table("projects")
