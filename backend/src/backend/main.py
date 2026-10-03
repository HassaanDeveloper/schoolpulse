from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import classes, me, schools, students
from backend.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{settings.API_V1_PREFIX}/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "schoolpulse-api",
    }


app.include_router(me.router, prefix=f"{settings.API_V1_PREFIX}/me", tags=["me"])
app.include_router(schools.router, prefix=f"{settings.API_V1_PREFIX}/schools", tags=["schools"])
app.include_router(classes.router, prefix=f"{settings.API_V1_PREFIX}/classes", tags=["classes"])
app.include_router(students.router, prefix=f"{settings.API_V1_PREFIX}/students", tags=["students"])