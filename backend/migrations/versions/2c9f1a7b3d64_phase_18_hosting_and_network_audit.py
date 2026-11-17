"""phase 18: hosted apps and authorized network audit

Revision ID: 2c9f1a7b3d64
Revises: 1a15f178ed4d
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c9f1a7b3d64"
down_revision: str | Sequence[str] | None = "1a15f178ed4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hosted_apps",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("path_prefix", sa.String(length=255), nullable=False),
        sa.Column("upstream_port", sa.Integer(), nullable=True),
        sa.Column("root_path", sa.String(length=512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('static','proxy')", name="ck_hosted_apps_hosted_apps_kind_valid"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hosted_apps")),
        sa.UniqueConstraint("name", name=op.f("uq_hosted_apps_name")),
    )
    op.create_table(
        "scan_scopes",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("cidr", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=32), nullable=False),
        sa.Column("authorized_until", sa.DateTime(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name=op.f("fk_scan_scopes_owner_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_scopes")),
        sa.UniqueConstraint("cidr", name=op.f("uq_scan_scopes_cidr")),
    )
    op.create_table(
        "network_scans",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("ports", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("findings_count", sa.Integer(), nullable=False),
        sa.Column("initiated_by", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], name=op.f("fk_network_scans_initiated_by_users")),
        sa.ForeignKeyConstraint(["scope_id"], ["scan_scopes.id"], name=op.f("fk_network_scans_scope_id_scan_scopes")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_network_scans")),
    )
    op.create_table(
        "scan_findings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("scan_id", sa.String(length=32), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["network_scans.id"], name=op.f("fk_scan_findings_scan_id_network_scans")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_findings")),
    )


def downgrade() -> None:
    op.drop_table("scan_findings")
    op.drop_table("network_scans")
    op.drop_table("scan_scopes")
    op.drop_table("hosted_apps")
