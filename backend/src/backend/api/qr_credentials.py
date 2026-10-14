import logging
import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedUser, require_school_admin
from backend.db.models import (
    Class,
    School,
    Student,
    StudentQrCredential,
    StudentStatusEnum,
)
from backend.db.session import get_db
from backend.schemas.qr_credential import QrCredentialRead, QrCredentialStatusRead
from backend.services import qr_credentials

logger = logging.getLogger(__name__)

router = APIRouter()

# One request prints at most this many cards. A class is far below this; the
# cap keeps a single request small enough for a serverless function.
MAX_CARDS_PER_REQUEST = 200


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


def get_class_for_admin(
    db: Session, user: AuthenticatedUser, class_id: uuid.UUID
) -> Class:
    """Fetch a class in a school the caller administers, or 404."""
    school_class = db.query(Class).filter(Class.id == class_id).one_or_none()
    if (
        school_class is None
        or user.profile is None
        or school_class.school_id
        not in {
            m.school_id
            for m in user.profile.memberships
            if m.role.value == "school_admin"
        }
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found."
        )
    return school_class


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


@router.post(
    "/cards/class/{class_id}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Printable ID cards."}},
    summary="Issue QR credentials for a class and return printable ID cards (PDF)",
)
def post_class_cards(
    class_id: uuid.UUID,
    mode: Literal["missing", "all"] = "missing",
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Print cards for one class.

    mode=missing (default): only students who have no active card yet.
    mode=all: replace every student's card. Previously printed cards stop
    working immediately.

    The PDF is built before anything is saved, and the new credentials are
    stored in one transaction afterwards, so a failure leaves nothing changed.
    """
    school_class = get_class_for_admin(db, user, class_id)

    # The PDF library is loaded here, not at startup, so a problem with it can
    # only ever affect card printing and never login or scanning.
    try:
        from backend.services import id_cards
    except ImportError:
        logger.exception("card printing library is not available")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Card printing is not available right now.",
        )

    school = db.query(School).filter(School.id == school_class.school_id).one_or_none()
    if school is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found."
        )

    students = (
        db.query(Student)
        .filter(
            Student.class_id == school_class.id,
            Student.school_id == school_class.school_id,
            Student.status == StudentStatusEnum.active,
        )
        .order_by(Student.last_name, Student.first_name)
        .all()
    )
    if not students:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This class has no active students.",
        )

    if mode == "missing":
        with_card = set(
            db.scalars(
                select(StudentQrCredential.student_id).where(
                    StudentQrCredential.student_id.in_([s.id for s in students]),
                    StudentQrCredential.revoked_at.is_(None),
                )
            ).all()
        )
        targets = [s for s in students if s.id not in with_card]
        if not targets:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Every active student in this class already has a card. "
                    "Choose to replace all cards if you need new ones."
                ),
            )
    else:
        targets = students

    if len(targets) > MAX_CARDS_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many cards in one request (maximum {MAX_CARDS_PER_REQUEST}).",
        )

    class_label = (
        f"{school_class.name} - {school_class.section}"
        if school_class.section
        else school_class.name
    )
    tokens = {s.id: qr_credentials.generate_credential() for s in targets}

    pdf = id_cards.render_cards_pdf(
        school.name,
        [
            id_cards.CardData(
                student_name=f"{s.first_name} {s.last_name}".strip(),
                admission_number=s.admission_number,
                class_label=class_label,
                credential=tokens[s.id],
            )
            for s in targets
        ],
    )

    qr_credentials.replace_credentials_bulk(db, targets, tokens)

    # Never log the tokens themselves.
    logger.info(
        "issued %s card(s) for class %s (mode=%s) by profile %s",
        len(targets),
        school_class.id,
        mode,
        user.profile.id if user.profile else None,
    )

    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", class_label).strip("-").lower() or "class"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cards-{slug}.pdf"',
            "Cache-Control": "no-store",
        },
    )