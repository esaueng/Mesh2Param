"""Add indexes for bounded project, version, and job listings."""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "0002_list_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        table: {index["name"] for index in inspect(op.get_bind()).get_indexes(table)}
        for table in ("projects", "versions", "jobs")
    }
    if "ix_projects_updated_id" not in existing["projects"]:
        op.create_index("ix_projects_updated_id", "projects", ["updated_at", "id"])
    if "ix_versions_project_created_id" not in existing["versions"]:
        op.create_index(
            "ix_versions_project_created_id",
            "versions",
            ["project_id", "created_at", "id"],
        )
    if "ix_jobs_created_id" not in existing["jobs"]:
        op.create_index("ix_jobs_created_id", "jobs", ["created_at", "id"])
    if "ix_jobs_project_status_created" not in existing["jobs"]:
        op.create_index(
            "ix_jobs_project_status_created",
            "jobs",
            ["project_id", "status", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_jobs_project_status_created", table_name="jobs")
    op.drop_index("ix_jobs_created_id", table_name="jobs")
    op.drop_index("ix_versions_project_created_id", table_name="versions")
    op.drop_index("ix_projects_updated_id", table_name="projects")
