import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import School, Student, StudentQrCredential

# 32 random bytes -> 43 URL-safe characters. Comfortably beyond brute-force reach.
CREDENTIAL_ENTROPY_BYTES = 32
CREDENTIAL_TOKEN_BYTES = 43


def generate_credential() -> str:
    """Return a cryptographically secure, opaque credential.

    Contains no student, school or user information of any kind.
    """
    return secrets.token_urlsafe(CREDENTIAL_ENTROPY_BYTES)


def hash_credential(raw_credential: str) -> str:
    """Return the SHA-256 hex digest that is stored in the database."""
    return hashlib.sha256(raw_credential.encode("utf-8")).hexdigest()


def get_active_credential(
    db: Session, student_id: uuid.UUID
) -> StudentQrCredential | None:
    return db.scalars(
        select(StudentQrCredential).where(
            StudentQrCredential.student_id == student_id,
            StudentQrCredential.revoked_at.is_(None),
        )
    ).first()


def get_latest_revoked_credential(
    db: Session, student_id: uuid.UUID
) -> StudentQrCredential | None:
    """The student's most recently revoked credential, if there is one.

    Lets the admin app tell "this code was revoked" apart from "this student
    never had a code", which an active-credential lookup alone cannot do.
    """
    return db.scalars(
        select(StudentQrCredential)
        .where(
            StudentQrCredential.student_id == student_id,
            StudentQrCredential.revoked_at.is_not(None),
        )
        .order_by(StudentQrCredential.revoked_at.desc())
    ).first()


def revoke_active_credential(db: Session, student_id: uuid.UUID) -> bool:
    """Revoke the student's active credential. Returns True if one existed."""
    credential = get_active_credential(db, student_id)
    if credential is None:
        return False
    credential.revoked_at = datetime.now(timezone.utc)
    return True


def issue_credential(
    db: Session,
    student: Student,
) -> tuple[StudentQrCredential, str, bool]:
    """Revoke any active credential, then issue a fresh one.

    Returns the credential row, the plaintext token (returned to the caller
    exactly once and never persisted) and whether a previous credential was
    revoked.

    Concurrency: on PostgreSQL the student's row is locked first, so two
    simultaneous "generate" requests for the same student run one after the
    other instead of racing. The second request then revokes the first one's
    code and issues its own, so exactly one credential stays active. The
    partial unique index `uq_qr_one_active_per_student` remains as the
    database-level backstop. SQLite ignores the lock, which is fine for tests.
    """
    db.execute(
        select(Student.id)
        .where(Student.id == student.id)
        .with_for_update(key_share=True)
    )

    revoked_previous = revoke_active_credential(db, student.id)
    # Make the revoke reach the database before the insert, so the new row never
    # collides with the old one under the one-active-credential index.
    db.flush()

    raw_credential = generate_credential()
    credential = StudentQrCredential(
        student_id=student.id,
        school_id=student.school_id,
        token_hash=hash_credential(raw_credential),
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)

    return credential, raw_credential, revoked_previous


def resolve_active_credential(db: Session, raw_credential: str) -> StudentQrCredential | None:
    """Look up an active credential by its plaintext token.

    Returns None when the credential is unknown or revoked.
    """
    if not raw_credential or len(raw_credential) > CREDENTIAL_TOKEN_BYTES + 16:
        return None

    return db.scalars(
        select(StudentQrCredential).where(
            StudentQrCredential.token_hash == hash_credential(raw_credential),
            StudentQrCredential.revoked_at.is_(None),
        )
    ).first()