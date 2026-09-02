import sys
import os
import time

sys.path.append(os.path.abspath("."))
from app import create_app
from models import (
    db,
    Institute,
    Teacher,
    Course,
    Subject,
    Settings,
    Timetable,
    SubjectCourse,
    TeacherLeave,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event
from sqlalchemy.engine import Engine


# Ensure FKs are enforced in SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


from migrations.relational_schema_migration import run_migration


def seed_db():
    i1 = Institute(
        name="Inst 1",
        institute_code="I1",
        admin_username="a1",
        admin_email="a1@x",
        admin_password="1",
    )
    i2 = Institute(
        name="Inst 2",
        institute_code="I2",
        admin_username="a2",
        admin_email="a2@x",
        admin_password="2",
    )
    db.session.add_all([i1, i2])
    db.session.commit()  # commit so they get IDs

    t1 = Teacher(
        institute_code="I1",
        teacher_id="T1",
        name="Alice",
        email="t1@x",
        departments="CS",
        available_days="Mon,Tue",
        max_hours=20,
    )
    t2 = Teacher(
        institute_code="I1",
        teacher_id="T2",
        name="Bob",
        email="t2@x",
        departments="CS",
        available_days="Mon",
        max_hours=20,
    )
    db.session.add_all([t1, t2])

    c1 = Course(institute_code="I1", class_id="CS1", department="CS", semester=1, division="A")
    c2 = Course(institute_code="I1", class_id="CS2", department="CS", semester=1, division="B")
    db.session.add_all([c1, c2])

    s1 = Subject(
        institute_code="I1",
        subject_code="S1",
        subject_name="Math",
        class_id="CS1",
        teacher_id="T1",
        required_hours=2,
    )
    s2 = Subject(
        institute_code="I1",
        subject_code="S2",
        subject_name="Physics",
        class_id="CS1,CS2",
        teacher_id="T2",
        required_hours=3,
    )  # common
    db.session.add_all([s1, s2])

    tt1 = Timetable(
        institute_code="I1",
        class_id="CS1",
        day_name="Mon",
        start_time="09",
        end_time="10",
        subject_name="Physics",
        teacher_name="Bob",
    )
    tt2 = Timetable(
        institute_code="I1",
        class_id="CS2",
        day_name="Mon",
        start_time="09",
        end_time="10",
        subject_name="Physics",
        teacher_name="Bob",
    )
    db.session.add_all([tt1, tt2])

    lv1 = TeacherLeave(
        institute_code="I1",
        teacher_id="T1",
        date=__import__("datetime").date(2026, 8, 26),
        status="Approved",
    )
    db.session.add(lv1)

    db.session.commit()
    print("Database populated successfully.")


def verify_fk_and_delete_policies():
    print("\n--- Testing FK Enforcement & Delete Policies ---")
    # Verify pragma
    res = db.session.execute(db.text("PRAGMA foreign_keys")).scalar()
    print(f"PRAGMA foreign_keys: {res}")

    # 1. Invalid FK Insert
    try:
        sc_bad = SubjectCourse(subject_id=999, course_id=999)
        db.session.add(sc_bad)
        db.session.commit()
        print("FAIL: Inserted invalid FK")
    except IntegrityError:
        db.session.rollback()
        print("PASS: Invalid FK insert rejected.")

    # 2. ON DELETE RESTRICT (Teacher with Subject)
    t2 = Teacher.query.filter_by(name="Bob").first()
    try:
        db.session.delete(t2)
        db.session.commit()
        print("FAIL: Deleted restricted Teacher!")
    except IntegrityError:
        db.session.rollback()
        print("PASS: Deleting active Teacher RESTRICTED.")

    # 3. ON DELETE CASCADE (Course)
    c1 = Course.query.filter_by(class_id="CS1").first()
    db.session.delete(c1)
    db.session.commit()
    sc_count = SubjectCourse.query.filter_by(course_id=c1.id).count()
    tt_count = Timetable.query.filter_by(course_id_fk=c1.id).count()
    if sc_count == 0 and tt_count == 0:
        print("PASS: Course deletion CASCADED to Timetable and SubjectCourse.")
    else:
        print("FAIL: Course CASCADE failed.")


def test_full_migration(app):

    with app.app_context():
        db.create_all()
        seed_db()

        counts_before = {
            "Teachers": Teacher.query.count(),
            "Courses": Course.query.count(),
            "Subjects": Subject.query.count(),
            "Timetable": Timetable.query.count(),
        }

        print("\n--- Running Migration ---")
        with db.session.begin_nested():
            run_migration()
        db.session.commit()
        print("Migration complete.")

        counts_after = {
            "Teachers": Teacher.query.count(),
            "Courses": Course.query.count(),
            "Subjects": Subject.query.count(),
            "Timetable": Timetable.query.count(),
        }

        print("\n--- Row Preservation Check ---")
        for k in counts_before:
            print(f"{k}: Before={counts_before[k]}, After={counts_after[k]}")
            assert counts_before[k] == counts_after[k]

        print("\n--- Verifying Relations ---")
        tts = Timetable.query.all()
        # They should share the same session_group_id
        assert tts[0].session_group_id == tts[1].session_group_id
        print("PASS: Common subjects accurately bound to session_group_id.")

        verify_fk_and_delete_policies()
