"""Schema drift check: migration 0002 vs the SQLAlchemy models.

Renders migration 0002 as offline PostgreSQL SQL, then compares it against the
DDL the models declare. Comparison is semantic (columns, types, nullability,
defaults, primary keys, unique sets, foreign keys with ON DELETE, indexes), so
purely cosmetic differences such as constraint naming or clause ordering do not
produce false mismatches.

Usage:  python check_migration.py
Exit code 0 = models and migration agree.
"""

import io
import re
import sys
from contextlib import redirect_stdout

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.db import models  # noqa: F401
from backend.db.base import Base

TABLES = [
    "student_qr_credentials",
    "attendance_records",
    "student_parent_links",
    "notifications",
]
PSEUDO_URL = "postgresql+psycopg://u:p@h:5432/d"


def squash(sql: str) -> str:
    return " ".join(sql.split())


def parse_create_table(sql: str) -> dict:
    """Extract the semantic parts of a CREATE TABLE statement."""
    body = re.search(r"CREATE TABLE \S+ \((.*)\)", squash(sql), re.S).group(1)

    columns = {}
    primary_key = None
    uniques = set()
    foreign_keys = set()

    # Split top-level clauses on commas that are not inside parentheses.
    clauses, depth, current = [], 0, ""
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            clauses.append(current)
            current = ""
        else:
            current += char
    clauses.append(current)

    for clause in (c.strip() for c in clauses):
        upper = clause.upper()
        unnamed_primary = re.fullmatch(r"PRIMARY KEY \((.*)\)", clause, re.I)
        unnamed_unique = re.fullmatch(r"UNIQUE \((.*)\)", clause, re.I)
        unnamed_fk = re.fullmatch(r"FOREIGN KEY\((.*?)\)\s+REFERENCES\s+(\S+)\s*(.*)", clause, re.I)

        if unnamed_primary:
            primary_key = tuple(sorted(squash(unnamed_primary.group(1)).split(",")))
        elif unnamed_unique:
            uniques.add(tuple(sorted(squash(unnamed_unique.group(1)).split(","))))
        elif unnamed_fk:
            cols = tuple(sorted(squash(unnamed_fk.group(1)).split(",")))
            ref = unnamed_fk.group(2)
            ondelete = re.search(r"ON DELETE (\w+)", unnamed_fk.group(3), re.I)
            foreign_keys.add((cols, ref, ondelete.group(1).upper() if ondelete else None))
        elif re.match(r"CONSTRAINT\s+\S+\s+PRIMARY KEY", clause, re.I):
            primary_key = tuple(sorted(squash(clause.split("(", 1)[1].rstrip(") ")).split(",")))
        elif re.match(r"CONSTRAINT\s+\S+\s+UNIQUE", clause, re.I):
            uniques.add(tuple(sorted(squash(clause.split("(", 1)[1].rstrip(") ")).split(","))))
        elif re.match(r"CONSTRAINT\s+\S+\s+FOREIGN KEY", clause, re.I):
            body2 = clause[clause.upper().index("FOREIGN KEY"):]
            fk = re.fullmatch(r"FOREIGN KEY\((.*?)\)\s+REFERENCES\s+(\S+)\s*(.*)", body2, re.I)
            cols = tuple(sorted(squash(fk.group(1)).split(",")))
            ondelete = re.search(r"ON DELETE (\w+)", fk.group(3), re.I)
            foreign_keys.add((cols, fk.group(2), ondelete.group(1).upper() if ondelete else None))
        else:
            name, _, rest = clause.partition(" ")
            parts = rest.split(" ", 1)
            column_type = parts[1].strip() if len(parts) > 1 else ""
            nullable = "NOT NULL" not in column_type.upper()
            default = None
            default_match = re.search(r"DEFAULT (\S+)", column_type, re.I)
            if default_match:
                default = default_match.group(1).strip("'")
            columns[name] = (
                squash(parts[0]).upper(),
                "TIMESTAMP" in column_type.upper(),
                nullable,
                default,
            )

    return {
        "columns": columns,
        "primary_key": primary_key,
        "uniques": uniques,
        "foreign_keys": foreign_keys,
    }


def parse_indexes(sql: str) -> set[str]:
    statements = [squash(s) for s in sql.split(";")]
    return {s for s in statements if s.startswith("CREATE INDEX")}


def model_ddl(table_name: str) -> tuple[str, set[str]]:
    table = Base.metadata.tables[table_name]
    engine = create_engine(PSEUDO_URL)
    create = str(CreateTable(table).compile(engine))
    indexes = {squash(str(CreateIndex(i).compile(engine))) for i in table.indexes}
    return create, indexes


def migration_sql() -> str:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)
    return buffer.getvalue()


def main() -> int:
    sql = migration_sql()
    migration_indexes = parse_indexes(sql)

    failures: list[str] = []

    for table_name in TABLES:
        migration_match = re.search(
            rf"CREATE TABLE {table_name} \(.*?\);", sql, re.S
        )
        if migration_match is None:
            failures.append(f"{table_name}: no CREATE TABLE in migration")
            continue

        model_table_sql, model_indexes = model_ddl(table_name)
        model = parse_create_table(model_table_sql)
        migration = parse_create_table(migration_match.group(0))

        for key in ("columns", "primary_key", "uniques", "foreign_keys"):
            if model[key] != migration[key]:
                failures.append(
                    f"{table_name}.{key}:\n  model    = {model[key]}\n  migration= {migration[key]}"
                )

        for index in sorted(model_indexes):
            if index not in migration_indexes:
                failures.append(f"{table_name}: index missing from migration -> {index}")

    print(f"tables compared      : {', '.join(TABLES)}")
    print(f"migration indexes    : {len(migration_indexes)}")
    if failures:
        for failure in failures:
            print("MISMATCH:", failure)
        print("RESULT: MISMATCH")
        return 1

    print("RESULT: MODELS AND MIGRATION AGREE")
    return 0


if __name__ == "__main__":
    sys.exit(main())