import pytest
from bs4 import BeautifulSoup
from models import db, Institute, Course, Teacher, Student, Timetable
from werkzeug.security import generate_password_hash
from datetime import date

def fake_live_week(*args, **kwargs):
    fake_record = Timetable(
        day_name="Mon",
        start_time="08:00 AM",
        end_time="08:45 AM",
        subject_name="Math",
        teacher_name="Prof. Test",
        class_id="FYCS-A"
    )
    fake_record.is_proxy = False
    fake_record.is_practical = False
    return {
        "week_start": date(2023, 1, 1),
        "week_end": date(2023, 1, 7),
        "working_days": ["Mon"],
        "day_dates": {"Mon": date(2023, 1, 2)},
        "records": [fake_record]
    }

def test_student_dash_mobile_layout(client, app, monkeypatch):
    with app.app_context():
        course = Course(institute_code="TEST01", class_id="FYCS-A", department="CS", semester=1, division="A")
        student = Student(institute_code="TEST01", name="Test Student", email="student@test.com", password="hash", class_id="FYCS-A")
        db.session.add_all([course, student])
        db.session.commit()
        student_id = student.id

    import utils.timetable_adapter
    monkeypatch.setattr(utils.timetable_adapter, "get_live_week_timetable", fake_live_week)

    with client.session_transaction() as sess:
        sess["student_id"] = student_id
        sess["institute_code"] = "TEST01"
        sess["class_id"] = "FYCS-A"

    response = client.get("/student_portal?inst_code=TEST01&class_id=FYCS-A")
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    desktop_table = soup.select_one('div.table-responsive.d-none.d-md-block')
    mobile_cards = soup.select_one('div.d-block.d-md-none.mobile-timetable')

    if desktop_table is None:
        print("HTML DUMP:\n", soup.prettify())
    assert desktop_table is not None, "Desktop timetable grid is missing responsive classes"
    assert mobile_cards is not None, "Mobile timetable agenda cards are missing"

def test_teacher_dash_mobile_layout(client, app, monkeypatch):
    with app.app_context():
        teacher = Teacher(institute_code="TEST01", teacher_id="T01", name="Prof. Test", email="teacher@test.com", password="hash", departments="CS", available_days="Mon", max_hours=10)
        db.session.add(teacher)
        db.session.commit()
        teacher_id = teacher.id

    import utils.timetable_adapter
    monkeypatch.setattr(utils.timetable_adapter, "get_live_week_timetable", fake_live_week)

    with client.session_transaction() as sess:
        sess["teacher_id"] = teacher_id
        sess["teacher_name"] = "Prof. Test"
        sess["institute_code"] = "TEST01"

    response = client.get("/teacher_dash")
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    desktop_table = soup.select_one('div.table-responsive.d-none.d-md-block')
    mobile_cards = soup.select_one('div.d-block.d-md-none.mobile-timetable')

    if desktop_table is None:
        print("HTML DUMP:\n", soup.prettify())
    assert desktop_table is not None, "Desktop timetable grid is missing responsive classes"
    assert mobile_cards is not None, "Mobile timetable agenda cards are missing"
    assert mobile_cards is not None, "Mobile timetable agenda cards are missing"

def test_admin_view_timetable_mobile_layout(client, app, monkeypatch):
    with app.app_context():
        course = Course(institute_code="TEST01", class_id="FYCS-A", department="CS", semester=1, division="A")
        admin_user = Institute.query.first()
        db.session.add(course)
        db.session.commit()
        admin_id = admin_user.id

    import utils.timetable_adapter
    monkeypatch.setattr(utils.timetable_adapter, "get_live_week_timetable", fake_live_week)

    with client.session_transaction() as sess:
        sess["admin_id"] = admin_id
        sess["institute_code"] = "TEST01"

    response = client.get("/view_timetable?class_id=FYCS-A")
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, 'html.parser')

    desktop_table = soup.select_one('div.table-responsive.d-none.d-md-block')
    mobile_cards = soup.select_one('div.d-block.d-md-none.mobile-timetable')

    assert desktop_table is not None, "Desktop timetable grid is missing responsive classes"
    assert mobile_cards is not None, "Mobile timetable agenda cards are missing"

def test_uncovered_token_display(client, app, monkeypatch):
    with app.app_context():
        course = Course(institute_code="TEST01", class_id="FYCS-A", department="CS", semester=1, division="A")
        db.session.add(course)
        db.session.commit()

    def fake_live_week_uncovered(*args, **kwargs):
        fake_record = Timetable(
            day_name="Mon",
            start_time="08:00 AM",
            end_time="08:45 AM",
            subject_name="Math",
            teacher_name="__UNCOVERED__",
            class_id="FYCS-A"
        )
        fake_record.is_proxy = False
        fake_record.is_practical = False
        return {
            "week_start": date(2023, 1, 1),
            "week_end": date(2023, 1, 7),
            "working_days": ["Mon"],
            "day_dates": {"Mon": date(2023, 1, 2)},
            "records": [fake_record]
        }

    import utils.timetable_adapter
    monkeypatch.setattr(utils.timetable_adapter, "get_live_week_timetable", fake_live_week_uncovered)

    with client.session_transaction() as sess:
        sess["admin_id"] = 1
        sess["institute_code"] = "TEST01"

    response = client.get("/view_timetable?class_id=FYCS-A")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()

    assert "__UNCOVERED__" not in text, "Raw __UNCOVERED__ token should not be visible as text to user"

    from utils.helpers import ScheduleConfig
    with app.app_context():
        sc = ScheduleConfig("TEST01")
        print("TEST01 TIME SLOTS:", sc.get_dynamic_time_slots())

    html_upper = html.upper()
    assert ("TEACHER ON LEAVE" in html_upper or "UNCOVERED" in html_upper or "UNASSIGNED PROXY" in html_upper or "PROXY NOT ASSIGNED" in html_upper), "Should show friendly uncovered message"

def test_mobile_empty_state(client, app, monkeypatch):
    with app.app_context():
        course = Course(institute_code="TEST01", class_id="FYCS-A", department="CS", semester=1, division="A")
        db.session.add(course)
        db.session.commit()

    def fake_live_week_empty(*args, **kwargs):
        return {
            "week_start": date(2023, 1, 1),
            "week_end": date(2023, 1, 7),
            "working_days": ["Mon"],
            "day_dates": {"Mon": date(2023, 1, 2)},
            "records": []
        }

    import utils.timetable_adapter
    monkeypatch.setattr(utils.timetable_adapter, "get_live_week_timetable", fake_live_week_empty)

    with client.session_transaction() as sess:
        sess["admin_id"] = 1
        sess["institute_code"] = "TEST01"

    response = client.get("/view_timetable?class_id=FYCS-A")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    assert "No lectures scheduled" in html or "No schedule for today" in html, "Should show empty state for mobile"
