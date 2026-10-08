import json
import threading
import time
import urllib.request
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import RoleEnum, UserProfile
from backend.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)

_JWKS_TTL_SECONDS = 600
_JWKS_MIN_REFETCH_SECONDS = 60
_jwks_lock = threading.Lock()
_jwks_cache: dict = {"keys": {}, "fetched_at": None}


@dataclass(frozen=True)
class AuthenticatedUser:
    auth_user_id: str
    email: str | None
    profile: UserProfile | None


def _invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _auth_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication is not configured on this server.",
    )


def _supabase_base() -> str:
    base = (settings.SUPABASE_URL or "").rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise _auth_unavailable()
    return base


def _fetch_jwks() -> dict[str, dict]:
    url = f"{_supabase_base()}/auth/v1/.well-known/jwks.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise _auth_unavailable()
    return {k["kid"]: k for k in payload.get("keys", []) if k.get("kid")}


def _get_signing_key(kid: str):
    now = time.monotonic()
    with _jwks_lock:
        key = _jwks_cache["keys"].get(kid)
        fetched_at = _jwks_cache["fetched_at"]
        if fetched_at is not None:
            age = now - fetched_at
            if key is not None and age < _JWKS_TTL_SECONDS:
                return key
            if key is None and age < _JWKS_MIN_REFETCH_SECONDS:
                return None
        keys = _fetch_jwks()
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        return keys.get(kid)


def decode_access_token(token: str) -> dict:
    from jose import jwt
    from jose.exceptions import JOSEError

    verify_aud = bool(settings.SUPABASE_JWT_AUDIENCE)

    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")

        if alg == "HS256":
            secret = settings.SUPABASE_JWT_SECRET
            if not secret:
                raise _auth_unavailable()
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=settings.SUPABASE_JWT_AUDIENCE,
                options={"verify_aud": verify_aud},
            )
        elif alg in ("ES256", "RS256"):
            kid = header.get("kid")
            if not kid:
                raise _invalid_token()
            jwk = _get_signing_key(kid)
            if jwk is None:
                raise _invalid_token()
            claims = jwt.decode(
                token,
                jwk,
                algorithms=[alg],
                audience=settings.SUPABASE_JWT_AUDIENCE,
                issuer=f"{_supabase_base()}/auth/v1",
                options={"verify_aud": verify_aud},
            )
        else:
            raise _invalid_token()
    except JOSEError:
        raise _invalid_token()

    if not claims.get("sub"):
        raise _invalid_token()

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
