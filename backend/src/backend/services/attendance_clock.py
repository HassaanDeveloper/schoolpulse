from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.db.models import School


def get_timezone(name: str | None) -> ZoneInfo:
    """Resolve an IANA timezone name, falling back to Asia/Karachi."""
    if not name:
        return ZoneInfo("Asia/Karachi")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Asia/Karachi")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def school_local_now(db: Session, school: School) -> datetime:
    return utc_now().astimezone(get_timezone(school.timezone))


def school_local_date(db: Session, school: School) -> date:
    """The attendance date for the school, in the school's own timezone."""
    return school_local_now(db, school).date()