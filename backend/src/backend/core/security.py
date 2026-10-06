from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import RoleEnum, UserProfile
from backend.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    auth_user_id: str
    email: str | None
    profile: UserProfile | None


def decode_access_token(token: str) -> dict:
    from jose import jwt
    from jose.exceptions import JWTError

    secret = settings.SUPABASE_JWT_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            options={"verify_aud": bool(settings.SUPABASE_JWT_AUDIENCE)},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return claims


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(credentials.credentials)
    auth_user_id = claims["sub"]

    profile = (
        db.query(UserProfile)
        .filter(UserProfile.auth_user_id == auth_user_id)
        .one_or_none()
    )

    return AuthenticatedUser(
        auth_user_id=auth_user_id,
        email=claims.get("email"),
        profile=profile,
    )


def require_profile(user: AuthenticatedUser) -> UserProfile:
    if user.profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No user profile is associated with this account.",
        )
    return user.profile


def require_school_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    profile = require_profile(user)
    has_admin = (
        profile.memberships is not None
        and any(m.role == RoleEnum.school_admin for m in profile.memberships)
    )
    if not has_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="School administrator privileges are required.",
        )
    return user


def require_teacher_or_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    profile = require_profile(user)
    allowed = {RoleEnum.school_admin, RoleEnum.teacher}
    has_role = profile.memberships is not None and any(
        m.role in allowed for m in profile.memberships
    )
    if not has_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher or school administrator privileges are required.",
        )
    return user


def require_parent(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Day 5: guard for the parent self-service endpoints.

    The parent routes live under `/me`, which every authenticated user can
    read, so the role has to be re-checked here. A staff-only account must get
    403 rather than silently receiving empty parent data.
    """
    profile = require_profile(user)
    has_parent = profile.memberships is not None and any(
        m.role == RoleEnum.parent for m in profile.memberships
    )
    if not has_parent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Parent privileges are required.",
        )
    return user