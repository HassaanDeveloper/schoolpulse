"""day 3: student qr credentials and attendance records

Revision ID: 0002_day3_attendance
Revises: 0001_day2
Create Date: 2026-10-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_day3_attendance"
down_revision: Union[str, None] = "0001_day2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schools need an IANA timezone so the attendance date can be calculated in
    # the school's own local day rather than the server's UTC day.
    op.add_column(
        "schools",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Asia/Karachi",
        ),
    )

    op.create_table(
        "student_qr_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        # Only the SHA-256 hash of the credential is stored.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_student_qr_credentials_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name="fk_student_qr_credentials_school_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_qr_credentials"),
        sa.UniqueConstraint("token_hash", name="uq_student_qr_credentials_token_hash"),
    )
    op.create_index(
        "ix_qr_credential_student_id",
        "student_qr_credentials",
        ["student_id"],
    )
    op.create_index(
        "ix_qr_credential_school_id",
        "student_qr_credentials",
        ["school_id"],
    )
    op.create_index(
        "ix_qr_credential_active",
        "student_qr_credentials",
        ["student_id", "revoked_at"],
    )

    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("arrival_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrival_scanned_by", sa.Uuid(), nullable=True),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departure_scanned_by", sa.Uuid(), nullable=True),
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
            name="fk_attendance_records_school_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name="fk_attendance_records_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["arrival_scanned_by"],
            ["user_profiles.id"],
            name="fk_attendance_records_arrival_scanned_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["departure_scanned_by"],
            ["user_profiles.id"],
            name="fk_attendance_records_departure_scanned_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_records"),
        # Guarantees at most one attendance record per student per school day.
        sa.UniqueConstraint(
            "student_id",
            "attendance_date",
            name="uq_attendance_student_date",
        ),
    )
    op.create_index(
        "ix_attendance_school_id", "attendance_records", ["school_id"]
    )
    op.create_index(
        "ix_attendance_school_date",
        "attendance_records",
        ["school_id", "attendance_date"],
    )
    op.create_index(
        "ix_attendance_student_id", "attendance_records", ["student_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_student_id", table_name="attendance_records")
    op.drop_index("ix_attendance_school_date", table_name="attendance_records")
    op.drop_index("ix_attendance_school_id", table_name="attendance_records")
    op.drop_table("attendance_records")

    op.drop_index("ix_qr_credential_active", table_name="student_qr_credentials")
    op.drop_index("ix_qr_credential_school_id", table_name="student_qr_credentials")
    op.drop_index("ix_qr_credential_student_id", table_name="student_qr_credentials")
    op.drop_table("student_qr_credentials")

    op.drop_column("schools", "timezone")