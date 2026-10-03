import os
import uuid

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-for-signing-tokens")

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.db import models  # noqa: F401
from backend.db.base import Base
from backend.db.models import RoleEnum, School, SchoolMembership, UserProfile
from backend.db.session import get_db
from backend.main import app

TEST_JWT_SECRET = "test-secret-for-signing-tokens"
SCHOOL_A = "11111111-1111-4111-8111-111111111111"
SCHOOL_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_token(user_id: str, email: str | None = None) -> str:
    claims = {
        "sub": user_id,
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "role": "authenticated",
        "exp": 9999999999,
    }
    if email:
        claims["email"] = email
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def seed_school(db, name: str = "Demo School") -> School:
    school = School(name=name, slug=name.lower().replace(" ", "-"))
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


def seed_user(
    db,
    auth_user_id: str,
    role: RoleEnum,
    school: School,
    email: str | None = None,
) -> UserProfile:
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.auth_user_id == auth_user_id)
        .one_or_none()
    )
    if profile is None:
        profile = UserProfile(auth_user_id=auth_user_id, email=email)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    db.add(
        SchoolMembership(school_id=school.id, user_id=profile.id, role=role)
    )
    db.commit()
    db.refresh(profile)
    return profile