import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.security import (
    AuthenticatedUser,
    get_current_user,
    require_school_admin,
    require_teacher_or_admin,
)
from backend.db.models import Class as ClassModel
from backend.db.models import School
from backend.db.models import Student as StudentModel
from backend.db.session import get_db
from backend.schemas.school_class import ClassCreate, ClassRead, ClassUpdate

router = APIRouter()


def accessible_school_ids(db: Session, user: AuthenticatedUser) -> list[uuid.UUID]:
    if user.profile is None:
        return []
    return [m.school_id for m in user.profile.memberships]


def resolve_school_id(
    db: Session,
    user: AuthenticatedUser,
    school_id: uuid.UUID | None,
) -> uuid.UUID:
    if school_id is None:
        ids = accessible_school_ids(db, user)
        if not ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to any school.",
            )
        if len(ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You belong to multiple schools. Specify school_id.",
            )
        return ids[0]

    if school_id not in accessible_school_ids(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this school.",
        )
    return school_id


@router.post("", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
def post_class(
    payload: ClassCreate,
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> ClassRead:
    target_school = resolve_school_id(db, user, school_id)

    school = db.query(School).filter(School.id == target_school).one_or_none()
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    new_class = ClassModel(
        school_id=school.id,
        name=payload.name.strip(),
        section=payload.section.strip() if payload.section else None,
        academic_year=payload.academic_year.strip() if payload.academic_year else None,
    )
    db.add(new_class)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A class with this name, section and academic year already exists.",
        )
    db.refresh(new_class)
    return ClassRead.model_validate(new_class)


@router.get("", response_model=list[ClassRead])
def list_classes(
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> list[ClassRead]:
    if school_id is not None:
        target_school = resolve_school_id(db, user, school_id)
        school_ids = [target_school]
    else:
        school_ids = accessible_school_ids(db, user)

    rows = db.query(ClassModel).filter(ClassModel.school_id.in_(school_ids)).order_by(ClassModel.name).all()
    return [ClassRead.model_validate(row) for row in rows]


@router.get("/{class_id}", response_model=ClassRead)
def get_class(
    class_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> ClassRead:
    row = db.query(ClassModel).filter(ClassModel.id == class_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    if row.school_id not in accessible_school_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    return ClassRead.model_validate(row)


@router.patch("/{class_id}", response_model=ClassRead)
def patch_class(
    class_id: uuid.UUID,
    payload: ClassUpdate,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> ClassRead:
    row = db.query(ClassModel).filter(ClassModel.id == class_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    if row.school_id not in accessible_school_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(row, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A class with this name, section and academic year already exists.",
        )
    db.refresh(row)
    return ClassRead.model_validate(row)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.query(ClassModel).filter(ClassModel.id == class_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    if row.school_id not in accessible_school_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")

    if db.query(StudentModel.id).filter(StudentModel.class_id == row.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a class that still has students.",
        )

    db.delete(row)
    db.commit()