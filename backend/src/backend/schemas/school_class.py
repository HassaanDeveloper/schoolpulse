import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    section: str | None = Field(default=None, max_length=50)
    academic_year: str | None = Field(default=None, max_length=20)


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    section: str | None = Field(default=None, max_length=50)
    academic_year: str | None = Field(default=None, max_length=20)


class ClassRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    section: str | None = None
    academic_year: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None