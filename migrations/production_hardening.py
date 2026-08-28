"""Add tenant uniqueness guarantees and high-value query indexes.

Run this once per existing database after taking and verifying a backup. The
migration is idempotent and checks legacy data for conflicting identifiers
before issuing any DDL.
"""

from pathlib import Path
import sys

from sqlalchemy import inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app  # noqa: E402
from models import db  # noqa: E402


UNIQUE_INDEXES = (
    ("uq_teacher_institute_identifier", "teacher", ("institute_code", "teacher_id")),
    ("uq_course_institute_class", "course", ("institute_code", "class_id")),
    ("uq_subject_institute_code", "subject", ("institute_code", "subject_code")),
    ("uq_settings_institute_key", "settings", ("institute_code", "key")),
)

QUERY_INDEXES = (
    ("ix_teacher_institute_name", "teacher", ("institute_code", "name")),
    ("ix_subject_institute_teacher", "subject", ("institute_code", "teacher_id")),
    (
        "ix_timetable_institute_class_slot",
        "timetable",
        ("institute_code", "class_id", "day_name", "start_time"),
    ),
    (
        "ix_timetable_institute_teacher_slot",
        "timetable",
        ("institute_code", "teacher_name", "day_name", "start_time"),
    ),
    ("ix_timetable_institute_date", "timetable", ("institute_code", "specific_date")),
    (
        "ix_update_request_institute_status",
        "teacher_update_request",
        ("institute_code", "status"),
    ),
    ("ix_calendar_institute_date", "academic_calendar", ("institute_code", "date")),
    (
        "ix_leave_institute_status_date",
        "teacher_leave",
        ("institute_code", "status", "date"),
    ),
    (
        "ix_leave_teacher_date",
        "teacher_leave",
        ("institute_code", "teacher_id", "date"),
    ),
    (
        "ix_notification_recipient",
        "notification",
        ("institute_code", "user_type", "user_id", "created_at"),
    ),
    (
        "ix_generation_history_institute_created",
        "generation_history",
        ("institute_code", "created_at"),
    ),
)


class DuplicateLegacyDataError(RuntimeError):
    """Raised when a unique tenant identifier already has conflicting rows."""


def _quoted(preparer, names):
    return ", ".join(preparer.quote(name) for name in names)


def _find_duplicates(connection, table_name, columns):
    preparer = connection.dialect.identifier_preparer
    quoted_table = preparer.quote(table_name)
    quoted_columns = _quoted(preparer, columns)
    statement = text(
        f"SELECT {quoted_columns}, COUNT(*) AS duplicate_count "
        f"FROM {quoted_table} GROUP BY {quoted_columns} HAVING COUNT(*) > 1"
    )
    return connection.execute(statement).mappings().fetchmany(10)


def _create_index(connection, name, table_name, columns, *, unique=False):
    preparer = connection.dialect.identifier_preparer
    unique_keyword = "UNIQUE " if unique else ""
    statement = (
        f"CREATE {unique_keyword}INDEX IF NOT EXISTS {preparer.quote(name)} "
        f"ON {preparer.quote(table_name)} ({_quoted(preparer, columns)})"
    )
    connection.execute(text(statement))


def run_migration():
    with db.engine.begin() as connection:
        existing_tables = set(inspect(connection).get_table_names())

        missing_tables = {
            table_name
            for _, table_name, _ in (*UNIQUE_INDEXES, *QUERY_INDEXES)
            if table_name not in existing_tables
        }
        if missing_tables:
            names = ", ".join(sorted(missing_tables))
            raise RuntimeError(f"Database schema is incomplete; missing tables: {names}")

        conflicts = []
        for _, table_name, columns in UNIQUE_INDEXES:
            duplicates = _find_duplicates(connection, table_name, columns)
            if duplicates:
                conflicts.append(f"{table_name}({', '.join(columns)}): {duplicates}")

        if conflicts:
            details = "\n".join(conflicts)
            raise DuplicateLegacyDataError(
                "Resolve these duplicate tenant identifiers before retrying:\n" + details
            )

        for name, table_name, columns in UNIQUE_INDEXES:
            _create_index(connection, name, table_name, columns, unique=True)

        for name, table_name, columns in QUERY_INDEXES:
            _create_index(connection, name, table_name, columns)


def execute():
    with app.app_context():
        run_migration()
    print("Production hardening migration completed successfully.")


if __name__ == "__main__":
    execute()
