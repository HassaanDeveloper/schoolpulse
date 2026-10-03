import re
import unicodedata

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.core.security import AuthenticatedUser, get_current_user
from backend.db.models import RoleEnum, School, SchoolMembership, UserProfile
from backend.db.session import get_db
from backend.schemas.school import SchoolCreate, SchoolRead

router = APIRouter()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "school"


def get_or_create_profile(
    db: Session, user: AuthenticatedUser, full_name: str | None = None
) -> UserProfile:
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.auth_user_id == user.auth_user_id)
        .one_or_none()
    )
    if profile is not None:
        return profile

    profile = UserProfile(
        auth_user_id=user.auth_user_id,
        email=user.email,
        full_name=full_name,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def unique_slug(db: Session, base: str) -> str:
    slug = base
    suffix = 1
    while db.query(School.id).filter(School.slug == slug).one_or_none() is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


@router.post(
    "",
    response_model=SchoolRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a school; the caller becomes its school administrator",
)
def post_school(
    payload: SchoolCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SchoolRead:
    profile = get_or_create_profile(db, user, payload.admin_name)

    school = School(name=payload.name.strip(), slug=unique_slug(db, slugify(payload.name)))
    db.add(school)
    db.commit()
    db.refresh(school)

    db.add(
        SchoolMembership(
            school_id=school.id,
            user_id=profile.id,
            role=RoleEnum.school_admin,
        )
    )
    db.commit()
    db.refresh(school)
    return SchoolRead.model_validate(school)