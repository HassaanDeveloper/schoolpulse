import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudentCreate(BaseModel):
    admission_number: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    class_id: uuid.UUID
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=20)
    status: str = "active"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("active", "inactive"):
            raise ValueError("status must be 'active' or 'inactive'")
        return v


class StudentUpdate(BaseModel):
    admission_number: Optional[str] = Field(default=None, min_length=1, max_length=50)
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    class_id: Optional[uuid.UUID] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "inactive"):
            raise ValueError("status must be 'active' or 'inactive'")
        return v


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    class_id: uuid.UUID
    admission_number: str
    first_name: str
    last_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StudentPage(BaseModel):
    items: list[StudentRead]
    total: int
    page: int
    page_size: int