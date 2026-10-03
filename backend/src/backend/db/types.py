import uuid as _uuid

from sqlalchemy import CHAR, types
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class GUID(types.TypeDecorator):
    """UUID column that maps to PostgreSQL UUID and to CHAR(36) elsewhere.

    This keeps a single set of SQLAlchemy models usable against the managed
    PostgreSQL database in every environment and against SQLite in tests.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, _uuid.UUID):
            value = _uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return value
        return _uuid.UUID(str(value))