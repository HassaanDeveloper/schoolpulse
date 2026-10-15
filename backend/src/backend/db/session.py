from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.core.config import settings
from backend.db.base import Base  # noqa: F401  (kept for existing imports)

CONNECT_TIMEOUT_SECONDS = 10
# Pooled connections are replaced after this long, so a connection the pooler
# has silently dropped is never handed to a request.
POOL_RECYCLE_SECONDS = 300


def build_engine_options(database_url: str) -> dict:
    """Engine settings that are safe for serverless hosting behind a pooler.

    * Pool sizes come from DB_POOL_SIZE / DB_MAX_OVERFLOW / DB_POOL_TIMEOUT, so
      they can be tuned per environment without a code change.
    * psycopg 3 prepares statements on the server after a few uses. That breaks
      behind Supabase's transaction pooler (the next request may land on a
      different server connection), so it is switched off. It costs almost
      nothing here.
    * A connect timeout stops a request from hanging forever if the database
      is unreachable.
    """
    options: dict = {"echo": False, "pool_pre_ping": True}
    url = make_url(database_url)

    if url.get_backend_name() == "sqlite":
        return options

    connect_args: dict = {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    if url.get_driver_name() == "psycopg":
        connect_args["prepare_threshold"] = None

    options.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE_SECONDS,
        connect_args=connect_args,
    )
    return options


engine = None
SessionLocal = None

if settings.DATABASE_URL:
    engine = create_engine(
        settings.DATABASE_URL, **build_engine_options(settings.DATABASE_URL)
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()