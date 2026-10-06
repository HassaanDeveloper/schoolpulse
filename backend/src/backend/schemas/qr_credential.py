import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QrCredentialRead(BaseModel):
    """Returned once, immediately after generation.

    The stored `token_hash` is never exposed.
    """

    student_id: uuid.UUID
    credential: str
    created_at: datetime | None = None
    revoked_previous: bool = False


class QrCredentialStatusRead(BaseModel):
    """Credential state without revealing the secret.

    `has_active_credential` alone cannot tell "revoked" from "never issued",
    because both leave no active row. `last_revoked_at` disambiguates them for
    the admin app: an issue date means the code was revoked, no dates at all
    means the student never had one.

    Day 6 addition; `last_revoked_at` is read from a column that already exists,
    so no migration is involved.
    """

    model_config = ConfigDict(from_attributes=True)

    student_id: uuid.UUID
    has_active_credential: bool
    created_at: datetime | None = None
    last_revoked_at: datetime | None = None