import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedUser, require_school_admin
from backend.db.models import Student
from backend.db.session import get_db
from backend.schemas.qr_credential import QrCredentialRead, QrCredentialStatusRead
from backend.services import qr_credentials

router = APIRouter()


def get_student_for_admin(
    db: Session, user: AuthenticatedUser, student_id: uuid.UUID
) -> Student:
    """Fetch a student the caller administers, or 404.

    Returning 404 (rather than 403) avoids disclosing that a student exists in
    another school.
    """
    student = db.query(Student).filter(Student.id == student_id).one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found."
        )

    if user.profile is None or student.school_id not in {
        m.school_id for m in user.profile.memberships if m.role.value == "school_admin"
    }:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found."
        )

    return student


@router.post(
    "/{student_id}/qr",
    response_model=QrCredentialRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate or regenerate a student's QR credential",
)
def post_qr_credential(
    student_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> QrCredentialRead:
    student = get_student_for_admin(db, user, student_id)

    credential, raw_credential, revoked_previous = qr_credentials.issue_credential(
        db, student
    )

    # `raw_credential` is returned to the admin exactly once and is never
    # stored or logged.
    return QrCredentialRead(
        student_id=student.id,
        credential=raw_credential,
        created_at=credential.created_at,
        revoked_previous=revoked_previous,
    )


@router.get(
    "/{student_id}/qr",
    response_model=QrCredentialStatusRead,
    summary="Check whether a student has an active QR credential",
)
def get_qr_credential_status(
    student_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> QrCredentialStatusRead:
    student = get_student_for_admin(db, user, student_id)
    credential = qr_credentials.get_active_credential(db, student.id)
    revoked = qr_credentials.get_latest_revoked_credential(db, student.id)

    return QrCredentialStatusRead(
        student_id=student.id,
        has_active_credential=credential is not None,
        created_at=credential.created_at if credential else None,
        last_revoked_at=revoked.revoked_at if revoked else None,
    )


@router.delete(
    "/{student_id}/qr",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a student's active QR credential",
)
def delete_qr_credential(
    student_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> None:
    student = get_student_for_admin(db, user, student_id)

    if not qr_credentials.revoke_active_credential(db, student.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active QR credential to revoke.",
        )

    db.commit()