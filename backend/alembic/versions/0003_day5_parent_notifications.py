"""day 5: parent linking and in-app notifications

Revision ID: 0003_day5_parent_notifications
Revises: 0002_day3_attendance
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_day5_parent_notifications"
down_revision: Union[str, None] = "0002_day3_attendance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # An explicit guardian relationship. Parents cannot claim students; a school
    # administrator creates this row.
    op.create_table(
        "student_parent_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("parent_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name="fk_student_parent_links_school_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_student_parent_links_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_user_id"],
            ["user_profiles.id"],
            name="fk_student_parent_links_parent_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_parent_links"),
        sa.UniqueConstraint(
            "student_id", "parent_user_id", name="uq_student_parent_link"
        ),
    )
    op.create_index(
        "ix_parent_link_school_id", "student_parent_links", ["school_id"]
    )
    op.create_index(
        "ix_parent_link_student_id", "student_parent_links", ["student_id"]
    )
    op.create_index(
        "ix_parent_link_parent_user_id", "student_parent_links", ["parent_user_id"]
    )

    # In-app notifications. `status` tracks delivery to SchoolPulse itself, not
    # to any external channel.
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("parent_user_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_id", sa.Uuid(), nullable=True),
        sa.Column(
            "type",
            sa.Enum("arrival", "departure", name="notificationtypeenum"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        # The attendance event time, used to order the parent's inbox.
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "sent", "failed", name="notificationstatusenum"),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name="fk_notifications_school_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_user_id"],
            ["user_profiles.id"],
            name="fk_notifications_parent_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_notifications_student_id",
            ondelete="CASCADE",
        ),
        # Deleting an attendance record removes the notices derived from it.
        sa.ForeignKeyConstraint(
            ["attendance_id"],
            ["attendance_records.id"],
            name="fk_notifications_attendance_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        # One notice per parent, per attendance record, per type. This is what
        # makes a repeated scan harmless.
        sa.UniqueConstraint(
            "parent_user_id",
            "attendance_id",
            "type",
            name="uq_notification_parent_attendance_type",
        ),
    )
    op.create_index(
        "ix_notification_parent_user_id", "notifications", ["parent_user_id"]
    )
    op.create_index("ix_notification_student_id", "notifications", ["student_id"])
    op.create_index("ix_notification_school_id", "notifications", ["school_id"])
    op.create_index("ix_notification_created_at", "notifications", ["created_at"])
    op.create_index("ix_notification_status", "notifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_notification_status", table_name="notifications")
    op.drop_index("ix_notification_created_at", table_name="notifications")
    op.drop_index("ix_notification_school_id", table_name="notifications")
    op.drop_index("ix_notification_student_id", table_name="notifications")
    op.drop_index("ix_notification_parent_user_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index(
        "ix_parent_link_parent_user_id", table_name="student_parent_links"
    )
    op.drop_index("ix_parent_link_student_id", table_name="student_parent_links")
    op.drop_index("ix_parent_link_school_id", table_name="student_parent_links")
    op.drop_table("student_parent_links")

    # Dropping the table does not drop the enum types in PostgreSQL. They are
    # removed explicitly so a later re-upgrade does not fail with
    # "type notificationtypeenum already exists".
    op.execute("DROP TYPE IF EXISTS notificationstatusenum")
    op.execute("DROP TYPE IF EXISTS notificationtypeenum")