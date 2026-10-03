from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class MembershipRead(BaseModel):
    school_id: uuid.UUID
    school_name: str
    role: str


class UserRead(BaseModel):
    id: str
    email: str | None = None
    full_name: str | None = None


class MeRead(BaseModel):
    user: UserRead
    memberships: list[MembershipRead] = Field(default_factory=list)