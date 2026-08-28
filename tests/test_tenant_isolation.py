from models import Course, Institute, Teacher, TeacherLeave, db
from utils.leave_service import cancel_leave


def test_admin_cannot_open_another_institutes_course(app, client):
    with app.app_context():
        other_institute = Institute(
            name="Other Institute",
            institute_code="OTHER01",
            admin_username="other-admin",
            admin_email="other@example.com",
            admin_password="unused",
        )
        other_course = Course(
            institute_code="OTHER01",
            class_id="OTHER-CLASS",
            department="CS",
            semester=1,
            division="A",
        )
        db.session.add_all([other_institute, other_course])
        db.session.commit()
        other_course_id = other_course.id

    client.post(
        "/login_admin",
        data={
            "username": "admin",
            "password": "password123",
        },
    )
    response = client.get(f"/edit_course/{other_course_id}")

    assert response.status_code == 404


def test_teacher_cannot_cancel_another_teachers_leave(app):
    with app.app_context():
        first_teacher = Teacher(
            institute_code="TEST01",
            teacher_id="T1",
            name="First",
            email="first@example.com",
            departments="CS",
            available_days="Mon",
            max_hours=10,
        )
        second_teacher = Teacher(
            institute_code="TEST01",
            teacher_id="T2",
            name="Second",
            email="second@example.com",
            departments="CS",
            available_days="Mon",
            max_hours=10,
        )
        db.session.add_all([first_teacher, second_teacher])
        db.session.flush()
        leave = TeacherLeave(
            institute_code="TEST01",
            teacher_id="T2",
            date=__import__("datetime").date(2099, 1, 5),
        )
        db.session.add(leave)
        db.session.commit()

        success, _message = cancel_leave(
            leave.id,
            actor_name="First",
            institute_code="TEST01",
            teacher_id="T1",
        )

        assert success is False
        assert leave.status == "Pending"
