"""Concurrency check: N simultaneous scans of the demo student against the live API.

Uses only the fictional demo student (admission SP-DEMO-001). Before the run it
clears that student's attendance and notifications and issues a fresh QR
credential through the service layer; after the run it clears them again.

Required environment variables (set them in the terminal, never commit them):
    API_BASE_URL       e.g. https://schoolpulse-ten.vercel.app/api/v1
    SUPABASE_ANON_KEY  the public publishable key
    TEST_EMAIL         a teacher/admin account that can scan at the demo school
    TEST_PASSWORD      its password
Optional:
    SCAN_PATH          default /attendance/scan  (confirm in the API's /docs)

Run from the backend folder, with PYTHONPATH=src;.
"""

import argparse
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.core.config import settings
from backend.db.models import AttendanceRecord, Notification, Student
from backend.services import qr_credentials

DEMO_ADMISSION = "SP-DEMO-001"


def need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Set the {name} environment variable first.")
    return value


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def clear_demo_attendance(Session, student_id) -> int:
    with Session() as db:
        records = db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.student_id == student_id)
        ).all()
        ids = [r.id for r in records]
        if ids:
            db.query(Notification).filter(Notification.attendance_id.in_(ids)).delete(
                synchronize_session=False
            )
            db.query(AttendanceRecord).filter(AttendanceRecord.id.in_(ids)).delete(
                synchronize_session=False
            )
            db.commit()
        return len(ids)


def login(supabase_url: str, anon_key: str, email: str, password: str) -> str:
    response = httpx.post(
        f"{supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key},
        json={"email": email, "password": password},
        timeout=20,
    )
    if response.status_code != 200:
        raise SystemExit(
            f"Login failed ({response.status_code}). Check TEST_EMAIL, TEST_PASSWORD "
            "and SUPABASE_ANON_KEY."
        )
    return response.json()["access_token"]


def fire_scans(url: str, token: str, credential: str, count: int):
    barrier = threading.Barrier(count)
    headers = {"Authorization": f"Bearer {token}"}

    def one(_index: int):
        with httpx.Client(timeout=40) as client:
            barrier.wait()
            started = time.perf_counter()
            try:
                response = client.post(url, json={"credential": credential}, headers=headers)
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                return response.status_code, body.get("status"), time.perf_counter() - started
            except Exception as exc:  # noqa: BLE001
                return "ERROR", type(exc).__name__, time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(one, range(count)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10, help="Number of simultaneous scans.")
    parser.add_argument("--keep", action="store_true", help="Do not clear attendance afterwards.")
    args = parser.parse_args()

    api_base = need("API_BASE_URL").rstrip("/")
    anon_key = need("SUPABASE_ANON_KEY")
    email = need("TEST_EMAIL")
    password = need("TEST_PASSWORD")
    scan_url = api_base + os.environ.get("SCAN_PATH", "/attendance/scan")

    if not settings.DATABASE_URL or not settings.SUPABASE_URL:
        raise SystemExit("DATABASE_URL and SUPABASE_URL must be configured (backend/.env).")

    engine = create_engine(
        normalize_database_url(settings.DATABASE_URL),
        connect_args={"prepare_threshold": None},
        future=True,
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        student = db.scalars(
            select(Student).where(Student.admission_number == DEMO_ADMISSION)
        ).first()
        if student is None:
            raise SystemExit("Demo student SP-DEMO-001 not found. Run prepare_demo.py first.")
        student_id = student.id

    removed = clear_demo_attendance(Session, student_id)
    print(f"Cleared {removed} old attendance record(s) for the demo student.")

    with Session() as db:
        student = db.get(Student, student_id)
        _, credential, _ = qr_credentials.issue_credential(db, student)
    print("Issued a fresh test credential for the demo student.")

    token = login(settings.SUPABASE_URL, anon_key, email, password)
    # Warm the function so the scans below really overlap instead of cold-starting.
    httpx.get(f"{api_base}/me", headers={"Authorization": f"Bearer {token}"}, timeout=40)

    print(f"Firing {args.count} simultaneous scans at {scan_url} ...")
    results = fire_scans(scan_url, token, credential, args.count)

    outcome = Counter((http, status) for http, status, _ in results)
    print("\nResponses:")
    for (http, status), n in sorted(outcome.items(), key=lambda kv: str(kv[0])):
        print(f"  HTTP {http}  status={status}  x{n}")
    slowest = max(t for _, _, t in results)
    print(f"Slowest response: {slowest:.2f}s")

    with Session() as db:
        rows = db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.student_id == student_id)
        ).all()
        notices = db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.student_id == student_id
            )
        )
    arrivals = sum(1 for r in rows if r.arrival_at is not None)
    departures = sum(1 for r in rows if r.departure_at is not None)

    print("\nDatabase after the run:")
    print(f"  attendance rows : {len(rows)}   (must be exactly 1)")
    print(f"  with arrival    : {arrivals}")
    print(f"  with departure  : {departures}")
    print(f"  notifications   : {notices}")

    failures = [r for r in results if r[0] != 200]
    arrival_responses = sum(1 for _, status, _ in results if status == "ARRIVAL_RECORDED")
    passed = not failures and len(rows) == 1 and arrivals == 1 and arrival_responses == 1

    print()
    if passed:
        print("PASS: no errors, exactly one attendance row, exactly one arrival.")
    else:
        print("FAIL: see the numbers above.")
        if failures:
            print(f"  {len(failures)} request(s) did not return HTTP 200.")
    if departures:
        print(
            "NOTE: a departure was recorded within seconds of the arrival. A duplicate\n"
            "      tap is currently treated as the departure scan (known design gap)."
        )

    if not args.keep:
        clear_demo_attendance(Session, student_id)
        print("Demo attendance cleared again.")

    engine.dispose()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())