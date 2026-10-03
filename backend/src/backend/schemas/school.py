import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    admin_name: str | None = Field(default=None, max_length=255)


class SchoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime | None = None
    updated_at: datetime | None = None