from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from backend.core.security import AuthenticatedUser, get_current_user
from backend.db.models import SchoolMembership, UserProfile
from backend.db.session import get_db
from backend.schemas.account import MeRead, MembershipRead, UserRead

router = APIRouter()


@router.get("", response_model=MeRead, summary="Current user and school memberships")
def get_me(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeRead:
    profile: UserProfile | None = (
        db.query(UserProfile)
        .options(joinedload(UserProfile.memberships).joinedload(SchoolMembership.school))
        .filter(UserProfile.auth_user_id == user.auth_user_id)
        .one_or_none()
    )

    if profile is None:
        return MeRead(
            user=UserRead(id=user.auth_user_id, email=user.email, full_name=None),
            memberships=[],
        )

    memberships = [
        MembershipRead(
            school_id=m.school_id,
            school_name=m.school.name,
            role=m.role.value,
        )
        for m in profile.memberships
    ]

    return MeRead(
        user=UserRead(
            id=profile.auth_user_id,
            email=profile.email,
            full_name=profile.full_name,
        ),
        memberships=memberships,
    )