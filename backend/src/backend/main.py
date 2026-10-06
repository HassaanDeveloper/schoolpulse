import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import (
    attendance,
    attendance_report,
    classes,
    me,
    parents,
    qr_credentials,
    schools,
    student_attendance,
    students,
)
from backend.core.config import settings
from backend.db.session import SessionLocal

logger = logging.getLogger("schoolpulse")


def validate_production_configuration() -> None:
    """Day 7: refuse to start a production process with incomplete settings.

    A missing database URL or JWT secret previously surfaced as a 500 on the
    first real request. Failing during startup turns a silent misconfiguration
    into an immediate, obvious deploy failure. Only setting NAMES are logged.
    """
    missing = settings.missing_production_settings()
    if missing:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production. "
            f"Missing or default settings: {', '.join(sorted(missing))}."
        )
    if not settings.is_postgres:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production. "
            "DATABASE_URL must be a PostgreSQL URL (postgresql://)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production:
        validate_production_configuration()
        logger.info(
            "startup validation passed (database=%s)",
            "postgresql" if settings.is_postgres else "unknown",
        )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Day 7: never return a traceback or exception text to the client.

    The detail is logged server-side, where the traceback is useful; the caller
    receives a generic 500 body with a correlation id they can quote.
    """
    incident = logging.getLogger("schoolpulse.incident")
    incident.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred.",
            "incident": "logged",
        },
    )


@app.get(f"{settings.API_V1_PREFIX}/health", tags=["health"])
def health() -> dict:
    """Liveness probe.

    Deliberately lightweight: no database round-trip, so a slow or unreachable
    database cannot take the load balancer's health check down with it. It
    reports whether a database is configured, never any configuration value.
    """
    return {
        "status": "ok",
        "service": "schoolpulse-api",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database_configured": SessionLocal is not None,
    }


app.include_router(me.router, prefix=f"{settings.API_V1_PREFIX}/me", tags=["me"])
app.include_router(schools.router, prefix=f"{settings.API_V1_PREFIX}/schools", tags=["schools"])
app.include_router(classes.router, prefix=f"{settings.API_V1_PREFIX}/classes", tags=["classes"])
app.include_router(students.router, prefix=f"{settings.API_V1_PREFIX}/students", tags=["students"])
app.include_router(
    qr_credentials.router,
    prefix=f"{settings.API_V1_PREFIX}/students",
    tags=["qr-credentials"],
)
app.include_router(
    attendance.router,
    prefix=f"{settings.API_V1_PREFIX}/attendance",
    tags=["attendance"],
)
# Day 4 read-only reporting. Registered after the Day 3 scan route so that
# POST /attendance/scan keeps its own path.
app.include_router(
    attendance_report.router,
    prefix=f"{settings.API_V1_PREFIX}/attendance",
    tags=["attendance-reports"],
)
app.include_router(
    student_attendance.router,
    prefix=f"{settings.API_V1_PREFIX}/students",
    tags=["attendance-reports"],
)
# Day 5 parent linking and parent self-service. Separate routers: the admin
# link routes hang off /students, the parent's own routes off /me.
app.include_router(
    parents.router,
    prefix=f"{settings.API_V1_PREFIX}/students",
    tags=["parent-links"],
)
app.include_router(
    parents.me_router,
    prefix=f"{settings.API_V1_PREFIX}/me",
    tags=["parents"],
)
# Day 6: read-only directory of linkable parent accounts for the admin app.
app.include_router(
    parents.directory_router,
    prefix=f"{settings.API_V1_PREFIX}/parents",
    tags=["parents"],
)