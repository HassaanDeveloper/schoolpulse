"""Response schemas for the Day 4 attendance dashboard and history.

Deliberately minimal: these endpoints expose only what a dashboard needs and
never return date of birth, gender, QR credentials or token hashes.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from backend.services.attendance_status import AttendanceStatus


class AttendanceSummaryRead(BaseModel):
    """Headline counts for one school-local date.

    Invariant: absent + present + completed == total_students.
    """

    date: date
    school_id: uuid.UUID
    school_name: str
    class_id: uuid.UUID | None = None
    total_students: int = Field(ge=0)
    absent: int = Field(ge=0)
    present: int = Field(ge=0)
    completed: int = Field(ge=0)


class TodayAttendanceItemRead(BaseModel):
    """One student's attendance for the requested day."""

    student_id: uuid.UUID
    student_name: str
    admission_number: str
    class_id: uuid.UUID
    class_name: str
    section: str | None = None
    status: AttendanceStatus
    arrival_at: datetime | None = None
    departure_at: datetime | None = None


class TodayAttendancePageRead(BaseModel):
    date: date
    school_id: uuid.UUID
    school_name: str
    items: list[TodayAttendanceItemRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class AttendanceHistoryRecordRead(BaseModel):
    """One day in a student's history. ABSENT days are included explicitly."""

    date: date
    status: AttendanceStatus
    arrival_at: datetime | None = None
    departure_at: datetime | None = None


class AttendanceHistoryPageRead(BaseModel):
    student_id: uuid.UUID
    student_name: str
    start_date: date
    end_date: date
    items: list[AttendanceHistoryRecordRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class StudentAttendanceSummaryRead(BaseModel):
    total_days: int = Field(ge=0)
    present_days: int = Field(ge=0)
    absent_days: int = Field(ge=0)
    completed_days: int = Field(ge=0)


class StudentAttendanceDetailRead(BaseModel):
    student: "StudentAttendanceOwnerRead"
    start_date: date
    end_date: date
    records: list[AttendanceHistoryRecordRead]
    summary: StudentAttendanceSummaryRead
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class StudentAttendanceOwnerRead(BaseModel):
    id: uuid.UUID
    name: str
    admission_number: str
    class_name: str
    section: str | None = None


StudentAttendanceDetailRead.model_rebuild()


class ClassOptionRead(BaseModel):
    """A class the caller may filter by, for populating the filter control."""

    id: uuid.UUID
    name: str
    section: str | None = None

    @property
    def label(self) -> str:
        return f"{self.name} - {self.section}" if self.section else self.name
