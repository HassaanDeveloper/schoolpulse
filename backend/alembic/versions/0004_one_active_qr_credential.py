"""Enforce at most one active QR credential per student.

Revision ID: 0004_one_active_qr_credential
Revises: 0003_day5_parent_notifications
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_one_active_qr_credential"
down_revision = "0003_day5_parent_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_qr_one_active_per_student",
        "student_qr_credentials",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_qr_one_active_per_student", table_name="student_qr_credentials")
