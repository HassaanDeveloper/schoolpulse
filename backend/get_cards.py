"""Download printable ID cards for one class from the live API (local tool).

Environment variables (set them in the terminal, never commit them):
    API_BASE_URL       e.g. https://schoolpulse-ten.vercel.app/api/v1
    SUPABASE_ANON_KEY  the public publishable key
    TEST_EMAIL         a school admin account
    TEST_PASSWORD      its password
Optional:
    CARDS_PREFIX       default /students (where the QR router is mounted)

Usage (from the backend folder, PYTHONPATH=src;.):
    python get_cards.py --class-name "Grade 5" --section A
    python get_cards.py --class-name "Grade 5" --section A --replace-all
"""

import argparse
import os
import sys

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.core.config import settings
from backend.db.models import Class, School


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


def login(supabase_url: str, anon_key: str, email: str, password: str) -> str:
    response = httpx.post(
        f"{supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key},
        json={"email": email, "password": password},
        timeout=20,
    )
    if response.status_code != 200:
        raise SystemExit(f"Login failed ({response.status_code}).")
    return response.json()["access_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--school", default="Karachi Model School")
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--section", default=None)
    parser.add_argument("--replace-all", action="store_true",
                        help="Issue new cards for EVERY student (old printed cards stop working).")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    api_base = need("API_BASE_URL").rstrip("/")
    anon_key = need("SUPABASE_ANON_KEY")
    email = need("TEST_EMAIL")
    password = need("TEST_PASSWORD")
    prefix = os.environ.get("CARDS_PREFIX", "/students")

    engine = create_engine(
        normalize_database_url(settings.DATABASE_URL),
        connect_args={"prepare_threshold": None},
        future=True,
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        query = (
            select(Class)
            .join(School, School.id == Class.school_id)
            .where(School.name == args.school, Class.name == args.class_name)
        )
        if args.section:
            query = query.where(Class.section == args.section)
        school_class = db.scalars(query).first()
        if school_class is None:
            raise SystemExit("Class not found. Check --school, --class-name and --section.")
        class_id = school_class.id
    engine.dispose()

    token = login(settings.SUPABASE_URL, anon_key, email, password)
    mode = "all" if args.replace_all else "missing"
    response = httpx.post(
        f"{api_base}{prefix}/cards/class/{class_id}",
        params={"mode": mode},
        headers={"Authorization": f"Bearer {token}"},
        timeout=90,
    )

    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text[:200]
        print(f"Request failed: HTTP {response.status_code} - {detail}")
        return 1

    out = args.out or f"cards-{args.class_name}-{args.section or 'all'}.pdf".replace(" ", "-").lower()
    with open(out, "wb") as handle:
        handle.write(response.content)
    print(f"Saved {out} ({len(response.content) // 1024} KB), mode={mode}.")
    print("The PDF contains live QR codes. Print it, then delete the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())