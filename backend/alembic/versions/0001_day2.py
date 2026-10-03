"""day 2: auth tenancy, school memberships, classes and students

Revision ID: 0001_day2
Revises:
Create Date: 2026-10-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_day2"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

role_enum = postgresql.ENUM(
    "school_admin",
    "teacher",
    "parent",
    name="roleenum",
    create_type=False,
)
student_status_enum = postgresql.ENUM(
    "active",
    "inactive",
    name="studentstatusenum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    role_enum.create(bind, checkfirst=True)
    student_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "schools",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_schools"),
        sa.UniqueConstraint("slug", name="uq_schools_slug"),
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auth_user_id", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_user_profiles"),
        sa.UniqueConstraint("auth_user_id", name="uq_user_profiles_auth_user_id"),
    )

    op.create_table(
        "school_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", role_enum, nullable=False),
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
            name="fk_school_memberships_school_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_profiles.id"],
            name="fk_school_memberships_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_school_memberships"),
        sa.UniqueConstraint(
            "school_id", "user_id", name="uq_membership_school_user"
        ),
    )
    op.create_index("ix_membership_school_id", "school_memberships", ["school_id"])
    op.create_index("ix_membership_user_id", "school_memberships", ["user_id"])

    op.create_table(
        "classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("section", sa.String(length=50), nullable=True),
        sa.Column("academic_year", sa.String(length=20), nullable=True),
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
            name="fk_classes_school_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_classes"),
        sa.UniqueConstraint(
            "school_id",
            "name",
            "section",
            "academic_year",
            name="uq_class_school_name_section_year",
        ),
    )
    op.create_index("ix_class_school_id", "classes", ["school_id"])

    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admission_number", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            student_status_enum,
            server_default="active",
            nullable=False,
        ),
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
            name="fk_students_school_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            name="fk_students_class_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_students"),
        sa.UniqueConstraint(
            "school_id", "admission_number", name="uq_student_school_admission"
        ),
    )
    op.create_index("ix_student_school_id", "students", ["school_id"])
    op.create_index("ix_student_class_id", "students", ["class_id"])


def downgrade() -> None:
    op.drop_index("ix_student_class_id", table_name="students")
    op.drop_index("ix_student_school_id", table_name="students")
    op.drop_table("students")

    op.drop_index("ix_class_school_id", table_name="classes")
    op.drop_table("classes")

    op.drop_index("ix_membership_user_id", table_name="school_memberships")
    op.drop_index("ix_membership_school_id", table_name="school_memberships")
    op.drop_table("school_memberships")

    op.drop_table("user_profiles")
    op.drop_table("schools")

    bind = op.get_bind()
    student_status_enum.drop(bind, checkfirst=True)
    role_enum.drop(bind, checkfirst=True)