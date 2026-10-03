import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.security import (
    AuthenticatedUser,
    get_current_user,
    require_school_admin,
    require_teacher_or_admin,
)
from backend.db.models import Class as ClassModel
from backend.db.models import Student as StudentModel
from backend.db.models import StudentStatusEnum
from backend.db.session import get_db
from backend.schemas.student import StudentCreate, StudentPage, StudentRead, StudentUpdate

router = APIRouter()

MAX_PAGE_SIZE = 100


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


def get_class_in_school(db: Session, class_id: uuid.UUID, school_id: uuid.UUID) -> ClassModel:
    row = db.query(ClassModel).filter(ClassModel.id == class_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    if row.school_id != school_id:
        raise HTTPException(
            status_code=422,
            detail="The selected class does not belong to this school.",
        )
    return row


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def post_student(
    payload: StudentCreate,
    school_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> StudentRead:
    target_school = resolve_school_id(db, user, school_id)
    get_class_in_school(db, payload.class_id, target_school)

    student = StudentModel(
        school_id=target_school,
        class_id=payload.class_id,
        admission_number=payload.admission_number.strip(),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        status=StudentStatusEnum(payload.status),
    )
    db.add(student)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this admission number already exists in this school.",
        )
    db.refresh(student)
    return StudentRead.model_validate(student)


@router.get("", response_model=StudentPage)
def list_students(
    school_id: uuid.UUID | None = Query(default=None),
    class_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> StudentPage:
    if school_id is not None:
        target_school = resolve_school_id(db, user, school_id)
        school_ids = [target_school]
    else:
        school_ids = accessible_school_ids(db, user)

    query = db.query(StudentModel).filter(StudentModel.school_id.in_(school_ids))

    if class_id is not None:
        query = query.filter(StudentModel.class_id == class_id)

    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                StudentModel.first_name.ilike(pattern),
                StudentModel.last_name.ilike(pattern),
                StudentModel.admission_number.ilike(pattern),
            )
        )

    total = query.count()
    rows = (
        query.order_by(StudentModel.first_name, StudentModel.last_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return StudentPage(
        items=[StudentRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{student_id}", response_model=StudentRead)
def get_student(
    student_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_teacher_or_admin),
    db: Session = Depends(get_db),
) -> StudentRead:
    row = db.query(StudentModel).filter(StudentModel.id == student_id).one_or_none()
    if row is None or row.school_id not in accessible_school_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    return StudentRead.model_validate(row)


@router.patch("/{student_id}", response_model=StudentRead)
def patch_student(
    student_id: uuid.UUID,
    payload: StudentUpdate,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> StudentRead:
    row = db.query(StudentModel).filter(StudentModel.id == student_id).one_or_none()
    if row is None or row.school_id not in accessible_school_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    data = payload.model_dump(exclude_unset=True)

    new_class_id = data.get("class_id")
    if new_class_id is not None:
        get_class_in_school(db, new_class_id, row.school_id)
        row.class_id = new_class_id

    if "admission_number" in data and data["admission_number"] is not None:
        row.admission_number = data["admission_number"].strip()
    if "first_name" in data and data["first_name"] is not None:
        row.first_name = data["first_name"].strip()
    if "last_name" in data and data["last_name"] is not None:
        row.last_name = data["last_name"].strip()
    if "date_of_birth" in data:
        row.date_of_birth = data["date_of_birth"]
    if "gender" in data:
        row.gender = data["gender"]
    if "status" in data and data["status"] is not None:
        row.status = StudentStatusEnum(data["status"])

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this admission number already exists in this school.",
        )
    db.refresh(row)
    return StudentRead.model_validate(row)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_student(
    student_id: uuid.UUID,
    user: AuthenticatedUser = Depends(require_school_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.query(StudentModel).filter(StudentModel.id == student_id).one_or_none()
    if row is None or row.school_id not in accessible_school_ids(db, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    row.status = StudentStatusEnum.inactive
    db.commit()
