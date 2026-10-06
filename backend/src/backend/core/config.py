from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "SchoolPulse API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = Field(default="")
    CORS_ORIGINS: str = "http://localhost:3000"

    SUPABASE_URL: str = Field(default="")
    SUPABASE_JWT_SECRET: str = Field(default="")
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # Day 7: exposed so `/health` can report whether the process is able to
    # serve traffic at all, without ever naming a value or a file path.
    APP_VERSION: str = Field(default="0.7.0")

    # Day 7: optional connection-pool sizing for managed PostgreSQL. Supabase
    # caps concurrent connections per project, so the pool is made explicit
    # rather than left to SQLAlchemy's default (5 + 10 overflow).
    DB_POOL_SIZE: int = Field(default=5)
    DB_MAX_OVERFLOW: int = Field(default=5)
    DB_POOL_TIMEOUT: int = Field(default=30)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        return origins if origins else ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    def missing_production_settings(self) -> List[str]:
        """Names of settings a production process cannot start without.

        Returns names only. Values are never included, so the result is safe to
        log or print.
        """
        required = {
            "DATABASE_URL": self.DATABASE_URL,
            "SUPABASE_URL": self.SUPABASE_URL,
            "SUPABASE_JWT_SECRET": self.SUPABASE_JWT_SECRET,
        }
        if self.cors_origins_list == ["http://localhost:3000"]:
            required["CORS_ORIGINS"] = ""
        return [name for name, value in required.items() if not value]

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith(("postgresql://", "postgres://"))


settings = Settings()