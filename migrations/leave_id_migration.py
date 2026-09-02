import sys
import os
import sqlalchemy

sys.path.append(os.path.abspath("."))
from app import create_app
from models import db, Timetable


def run_migration(app=None):
    if app is None:
        app = create_app()
    with app.app_context():
        inspector = sqlalchemy.inspect(db.engine)
        print("DB URL:", db.engine.url)
        columns = [col["name"] for col in inspector.get_columns("timetable")]

        if "leave_id" not in columns:
            print("Adding leave_id to timetable...")
            with db.engine.connect() as conn:
                conn.execute(
                    sqlalchemy.text(
                        "ALTER TABLE timetable ADD COLUMN leave_id INTEGER REFERENCES teacher_leave(id)"
                    )
                )
                conn.commit()
            print("Migration successful.")
        else:
            print("leave_id already exists.")


if __name__ == "__main__":
    run_migration()
