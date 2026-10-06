"""School membership resolution shared by the Day 2 and Day 4 endpoints.

Kept in one place so that tenant scoping is applied identically everywhere and
cannot drift between routers.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedUser, require_profile
from backend.db.models import Class, RoleEnum, School, Student, StudentParentLink, UserProfile


def accessible_school_ids(db: Session, user: AuthenticatedUser) -> list[uuid.UUID]:
    """School ids the caller is a member of, regardless of role."""
    profile = user.profile
    if profile is None:
        return []
    return [membership.school_id for membership in profile.memberships]


def staff_school_ids(db: Session, user: AuthenticatedUser) -> list[uuid.UUID]:
    """School ids where the caller holds an attendance-visible role.

    Parents have no attendance visibility at all, so a user who is only a parent
    at every school gets an empty list here.
    """
    profile = user.profile
    if profile is None:
        return []
    staff_roles = {RoleEnum.school_admin, RoleEnum.teacher}
    return [
        membership.school_id
        for membership in profile.memberships
        if membership.role in staff_roles
    ]


def resolve_school_id(
    db: Session,
    user: AuthenticatedUser,
    school_id: uuid.UUID | None,
    *,
    staff_only: bool = False,
) -> uuid.UUID:
    """Return the school the caller is operating on.

    A client-supplied `school_id` is never trusted on its own: it must match a
    school the caller actually belongs to. When the caller belongs to exactly
    one eligible school the id may be omitted entirely.
    """
    allowed = staff_school_ids(db, user) if staff_only else accessible_school_ids(db, user)

    if school_id is None:
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to any school.",
            )
        if len(allowed) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You belong to multiple schools. Specify school_id.",
            )
        return allowed[0]

    if school_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this school.",
        )
    return school_id


def resolve_staff_school(
    db: Session,
    user: AuthenticatedUser,
    school_id: uuid.UUID | None,
) -> School:
    """Resolve the school row for an attendance-visible caller."""
    profile = require_profile(user)
    staff_roles = {RoleEnum.school_admin, RoleEnum.teacher}
    if not any(m.role in staff_roles for m in profile.memberships):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher or school administrator privileges are required.",
        )

    target = resolve_school_id(db, user, school_id, staff_only=True)
    school = db.query(School).filter(School.id == target).one_or_none()
    if school is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )
    return school


def resolve_class(db: Session, class_id: uuid.UUID, school_id: uuid.UUID) -> Class:
    """Load a class, refusing any class outside `school_id`.

    A class belonging to another school is reported as missing so the API does
    not confirm that it exists.
    """
    row = db.query(Class).filter(Class.id == class_id).one_or_none()
    if row is None or row.school_id != school_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")
    return row


def resolve_student(db: Session, student_id: uuid.UUID, school_id: uuid.UUID) -> Student:
    """Load a student, refusing any student outside `school_id`."""
    row = db.query(Student).filter(Student.id == student_id).one_or_none()
    if row is None or row.school_id != school_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    return row


def resolve_admin_school_for_student(
    db: Session,
    user: AuthenticatedUser,
    student_id: uuid.UUID,
) -> School:
    """Resolve the school of a student for a school-admin link operation.

    The student id is globally unique, so the school follows from the student
    rather than from anything the client sends. The admin must actually be an
    admin of that school, which also answers the multi-school case without
    asking the caller to guess a `school_id`.
    """
    profile = require_profile(user)
    student = db.query(Student).filter(Student.id == student_id).one_or_none()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    is_admin_of_school = any(
        membership.school_id == student.school_id
        and membership.role == RoleEnum.school_admin
        for membership in profile.memberships
    )
    if not is_admin_of_school:
        # A cross-tenant admin is told the student does not exist rather than
        # that the student exists in a school they cannot administer.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    school = db.query(School).filter(School.id == student.school_id).one_or_none()
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    return school


def admin_school_ids(db: Session, user: AuthenticatedUser) -> list[uuid.UUID]:
    """School ids where the caller holds a `school_admin` membership."""
    profile = user.profile
    if profile is None:
        return []
    return [
        membership.school_id
        for membership in profile.memberships
        if membership.role == RoleEnum.school_admin
    ]


def resolve_admin_school(db: Session, user: AuthenticatedUser, school_id: uuid.UUID | None) -> School:
    """Resolve a school the caller administers.

    The school always comes from the caller's own admin memberships. A
    client-supplied `school_id` is honoured only when it matches one of them,
    and an admin of several schools is asked to choose rather than having the
    API guess.

    Used by the Day 6 admin directory screens, which have a school in hand
    rather than a student.
    """
    profile = require_profile(user)
    admin_ids = admin_school_ids(db, user)

    if not admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not administer any school.",
        )

    if school_id is None:
        if len(admin_ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You administer more than one school. Choose a school.",
            )
        target = admin_ids[0]
    elif school_id in admin_ids:
        target = school_id
    else:
        # A cross-tenant admin is told the school does not exist, so the route
        # cannot be used to discover another school's id.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )

    school = db.query(School).filter(School.id == target).one_or_none()
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")
    return school


def parent_school_ids(db: Session, user: AuthenticatedUser) -> list[uuid.UUID]:
    """School ids where the caller holds a parent membership."""
    profile = user.profile
    if profile is None:
        return []
    return [
        membership.school_id
        for membership in profile.memberships
        if membership.role == RoleEnum.parent
    ]


def resolve_parent_school(db: Session, user: AuthenticatedUser, school_id: uuid.UUID) -> School:
    """Resolve a school the caller is a parent of.

    Unlike staff, parents get an explicit `school_id` rather than an implicit
    single-school default, because a parent can be linked to children at more
    than one school and must be able to choose which one they are looking at.
    """
    if school_id not in parent_school_ids(db, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )
    school = db.query(School).filter(School.id == school_id).one_or_none()
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")
    return school


def linked_students(
    db: Session,
    parent: UserProfile,
    school_id: uuid.UUID | None = None,
) -> list[tuple[StudentParentLink, Student]]:
    """Every student this parent is linked to, as (link, student) pairs.

    The join is done from the link table outwards rather than from
    `students`, so a student outside the caller's school can never appear.
    """
    query = (
        db.query(StudentParentLink, Student)
        .join(Student, Student.id == StudentParentLink.student_id)
        .filter(StudentParentLink.parent_user_id == parent.id)
        .order_by(Student.first_name, Student.last_name, Student.id)
    )
    if school_id is not None:
        query = query.filter(StudentParentLink.school_id == school_id)
    return query.all()


def resolve_linked_student(
    db: Session,
    parent: UserProfile,
    student_id: uuid.UUID,
) -> Student:
    """Load a student only if a parent link exists for this parent.

    Unlinked students and students in another school are both reported as
    missing, so probing ids cannot reveal which students exist.
    """
    row = (
        db.query(Student)
        .join(StudentParentLink, StudentParentLink.student_id == Student.id)
        .filter(
            StudentParentLink.parent_user_id == parent.id,
            Student.id == student_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    return row


def resolve_parent_profile(db: Session, parent_user_id: uuid.UUID, school_id: uuid.UUID) -> UserProfile:
    """Load the profile a school is about to link, refusing unknown or non-parent profiles.

    A profile with no membership in the student's school, or whose only role
    there is staff, cannot be given parent access.
    """
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.id == parent_user_id)
        .one_or_none()
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent user not found.",
        )

    is_parent_here = any(
        membership.school_id == school_id and membership.role == RoleEnum.parent
        for membership in profile.memberships
    )
    if not is_parent_here:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That user does not hold a parent membership in this school.",
        )
    return profile
