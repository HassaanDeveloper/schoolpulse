import uuid
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    ARRIVAL_RECORDED = "ARRIVAL_RECORDED"
    DEPARTURE_RECORDED = "DEPARTURE_RECORDED"
    ALREADY_RECORDED = "ALREADY_RECORDED"


class ScanRequest(BaseModel):
    """Only the opaque credential is accepted from the client.

    No student_id, school_id, user_id, role or attendance_date is accepted, so
    a client cannot influence who is marked present.
    """

    credential: str = Field(min_length=1, max_length=256)


class ScannedStudent(BaseModel):
    """Minimal student identification returned to the scanner."""

    id: uuid.UUID
    name: str
    admission_number: str


class ScanResponse(BaseModel):
    status: ScanStatus
    student: ScannedStudent
    attendance_date: date
    arrival_at: datetime | None = None
    departure_at: datetime | None = None
    # When the current status was recorded. For ARRIVAL_RECORDED this is the
    # arrival, for DEPARTURE_RECORDED the departure, and for ALREADY_RECORDED
    # the departure if the day is already complete.
    timestamp: datetime | None = None