from sqlalchemy import inspect

from migrations.production_hardening import run_migration
from models import db


def test_production_hardening_migration_is_idempotent(app):
    with app.app_context():
        run_migration()
        run_migration()

        indexes = {index["name"] for index in inspect(db.engine).get_indexes("timetable")}

    assert "ix_timetable_institute_class_slot" in indexes
    assert "ix_timetable_institute_teacher_slot" in indexes
    assert "ix_timetable_institute_date" in indexes
