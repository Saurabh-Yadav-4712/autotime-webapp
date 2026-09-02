import pytest
from datetime import datetime, timedelta
from models import db, Teacher, TeacherLeave, Timetable, Subject, Course, Institute
from utils.proxy_engine import find_best_proxy
from utils.helpers import ScheduleConfig

def setup_test_data(app):
    inst_code = "TEST01"
    with app.app_context():
        Institute.query.filter_by(institute_code=inst_code).delete()
        Course.query.filter_by(institute_code=inst_code).delete()
        Teacher.query.filter_by(institute_code=inst_code).delete()
        Subject.query.filter_by(institute_code=inst_code).delete()
        Timetable.query.filter_by(institute_code=inst_code).delete()
        TeacherLeave.query.filter_by(institute_code=inst_code).delete()
        db.session.commit()

        inst = Institute(
            institute_code=inst_code,
            name="Test Institute",
            admin_username="admin",
            admin_email="admin@test.com",
            admin_password="pass",
        )
        db.session.add(inst)

        c1 = Course(institute_code=inst_code, class_id="FYCS-A", department="CS", semester=1, division="A")
        c2 = Course(institute_code=inst_code, class_id="FYIT-A", department="IT", semester=1, division="A")
        db.session.add_all([c1, c2])

        tA = Teacher(institute_code=inst_code, teacher_id="TA", name="Teacher A", email="a@t.com", departments="CS", available_days="Mon", max_hours=10)
        tB = Teacher(institute_code=inst_code, teacher_id="TB", name="Teacher B", email="b@t.com", departments="CS", available_days="Mon", max_hours=10)
        tC = Teacher(institute_code=inst_code, teacher_id="TC", name="Teacher C", email="c@t.com", departments="CS", available_days="Mon", max_hours=10)
        tD = Teacher(institute_code=inst_code, teacher_id="TD", name="Teacher D", email="d@t.com", departments="IT", available_days="Mon", max_hours=10)
        db.session.add_all([tA, tB, tC, tD])

        db.session.commit()

        # A teaches FYCS-A (DBMS)
        sA = Subject(institute_code=inst_code, subject_code="S1", subject_name="DBMS", class_id="FYCS-A", teacher_id="TA", required_hours=4)
        # B teaches FYCS-A (Python)
        sB = Subject(institute_code=inst_code, subject_code="S2", subject_name="Python", class_id="FYCS-A", teacher_id="TB", required_hours=4)
        # C teaches FYIT-A (AI) - same dept but diff class
        sC = Subject(institute_code=inst_code, subject_code="S3", subject_name="AI", class_id="FYIT-A", teacher_id="TC", required_hours=4)
        db.session.add_all([sA, sB, sC])
        db.session.commit()

        target_date = datetime(2026, 8, 31).date()  # Monday

        return inst_code, target_date

def test_proxy_hierarchy(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        # Setup: Affected session is DBMS taught by A
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="DBMS", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        schedule_config = ScheduleConfig(inst_code)

        # Test A: Same class wins
        # B teaches FYCS-A, C is same dept but doesn't teach FYCS-A. Both free.
        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher B"
        assert res["priority"] == "SAME_CLASS"

        # Test B: Same department fallback
        # Make B busy
        busy_b = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="Python", teacher_name="Teacher B")
        db.session.add(busy_b)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher C"
        assert res["priority"] == "SAME_DEPARTMENT"

        # Test C: Other department fallback
        # Make C busy
        busy_c = Timetable(institute_code=inst_code, class_id="FYIT-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="AI", teacher_name="Teacher C")
        db.session.add(busy_c)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher D"
        assert res["priority"] == "OTHER_DEPARTMENT"

def test_hard_constraints(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="DBMS", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        schedule_config = ScheduleConfig(inst_code)

        # Test F: Teacher on leave excluded
        # B is best, but put B on leave
        TeacherLeave.query.filter_by(institute_code=inst_code).delete()
        leave = TeacherLeave(institute_code=inst_code, teacher_id="TB", date=target_date, status="Approved")
        db.session.add(leave)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher C" # skips B

        db.session.delete(leave)
        db.session.commit()

        # Test G: Max workload excluded
        # B has max_hours=1. Give B 1 master lecture.
        tb = Teacher.query.filter_by(name="Teacher B").first()
        tb.max_hours = 1
        busy_b2 = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="10:00", end_time="11:00", subject_name="Python", teacher_name="Teacher B")
        db.session.add(busy_b2)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher C" # skips B due to workload

        # Test K: Nothing available
        tc = Teacher.query.filter_by(name="Teacher C").first()
        tc.max_hours = 0
        td = Teacher.query.filter_by(name="Teacher D").first()
        td.max_hours = 0
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"] is None
        assert res["reason"] == "NO_ELIGIBLE_PROXY"

def test_practical_block(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        # Practical: 2 slots
        lec1 = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="DBMS", teacher_name="Teacher A", session_group_id="G1")
        lec2 = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="10:00", end_time="11:00", subject_name="DBMS", teacher_name="Teacher A", session_group_id="G1")
        db.session.add_all([lec1, lec2])
        db.session.commit()

        schedule_config = ScheduleConfig(inst_code)

        # B is free for 09:00 but busy for 10:00
        busy_b = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="10:00", end_time="11:00", subject_name="Python", teacher_name="Teacher B")
        db.session.add(busy_b)
        db.session.commit()

        # B should be excluded for the whole block
        res = find_best_proxy(inst_code, [lec1, lec2], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher C"


def test_workload_calculation_with_proxies(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        schedule_config = ScheduleConfig(inst_code)

        # Test A: Existing proxy contributes to max workload
        # B has max_hours=3. Master workload=2. Existing proxies this week=1. Total=3.
        # New block length=1 -> exceeds max workload!
        tb = Teacher.query.filter_by(teacher_id="TB").first()
        tb.max_hours = 3

        # Master duties
        m1 = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Tue", start_time="09:00", end_time="10:00", subject_name="Python", teacher_name="Teacher B", teacher_id_fk=tb.id)
        m2 = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Wed", start_time="09:00", end_time="10:00", subject_name="Python", teacher_name="Teacher B", teacher_id_fk=tb.id)

        # Existing proxy this week
        px = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="11:00", end_time="12:00", subject_name="OS", teacher_name="Teacher B", teacher_id_fk=tb.id, is_proxy=True, specific_date=target_date)

        db.session.add_all([m1, m2, px])
        db.session.commit()

        # New block length 1
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="DBMS", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name != "Teacher B", "Teacher B should be rejected due to workload"

def test_historical_proxy_does_not_affect_fairness(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        schedule_config = ScheduleConfig(inst_code)

        tb = Teacher.query.filter_by(teacher_id="TB").first()
        tc = Teacher.query.filter_by(teacher_id="TC").first()

        # B has 10 historical proxies
        old_date = target_date - timedelta(days=14)
        for i in range(10):
            db.session.add(Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time=f"0{i}:00", end_time="00:00", subject_name="OS", teacher_name="Teacher B", teacher_id_fk=tb.id, is_proxy=True, specific_date=old_date))

        # C has 1 current proxy
        db.session.add(Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="08:00", end_time="00:00", subject_name="OS", teacher_name="Teacher C", teacher_id_fk=tc.id, is_proxy=True, specific_date=target_date))

        # Setup affected session for AI (C's subject), but B is same class
        # Wait, if B is same class, B wins priority anyway. Let's make both same priority.
        # B and C are Priority 1 if we make both teach FYCS-A.
        # But C teaches FYIT-A right now. Let's add FYCS-A class to C.
        s4 = Subject(institute_code=inst_code, subject_code="S4", subject_name="OS", class_id="FYCS-A", teacher_id="TC", required_hours=4)
        db.session.add(s4)
        db.session.commit()

        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="12:00", end_time="13:00", subject_name="DBMS", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        # B has 0 current proxies, C has 1 current proxy. B should win over C.
        assert res["teacher"].name == "Teacher B"

def test_date_specific_proxy_collision(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        schedule_config = ScheduleConfig(inst_code)

        # B is free in Master, but has specific_date proxy at 10 AM.
        tb = Teacher.query.filter_by(teacher_id="TB").first()
        px = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="10:00", end_time="11:00", subject_name="OS", teacher_name="Teacher B", teacher_id_fk=tb.id, is_proxy=True, specific_date=target_date)
        db.session.add(px)
        db.session.commit()

        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="10:00", end_time="11:00", subject_name="DBMS", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name != "Teacher B", "Teacher B must be rejected due to collision"

def test_multi_department_teacher(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        schedule_config = ScheduleConfig(inst_code)
        # D is IT. Let's change D to IT, CS
        td = Teacher.query.filter_by(teacher_id="TD").first()
        td.departments = "IT, CS"
        db.session.commit()

        # Lec for CS dept
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="15:00", end_time="16:00", subject_name="DBMS", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        # If D is CS, Priority 2. If D is IT, Priority 3.
        # But B and C are CS. Let's put B and C on leave so only D is left.
        TeacherLeave.query.filter_by(institute_code=inst_code).delete()
        tb = Teacher.query.filter_by(teacher_id="TB").first()
        tc = Teacher.query.filter_by(teacher_id="TC").first()
        l1 = TeacherLeave(institute_code=inst_code, teacher_id="TB", date=target_date, status="Approved")
        l2 = TeacherLeave(institute_code=inst_code, teacher_id="TC", date=target_date, status="Approved")
        db.session.add_all([l1, l2])
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher D"
        assert res["priority"] == "SAME_DEPARTMENT"

def test_same_subject_preference(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        schedule_config = ScheduleConfig(inst_code)

        # Both B and C are Priority 1 (same class). B teaches Python. C teaches AI.
        # Affected session is Python!
        tc = Teacher.query.filter_by(teacher_id="TC").first()
        s4 = Subject(institute_code=inst_code, subject_code="S4", subject_name="AI", class_id="FYCS-A", teacher_id="TC", required_hours=4)
        db.session.add(s4)
        db.session.commit()

        # Target: Python
        sb = Subject.query.filter_by(subject_code="S2").first()
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="16:00", end_time="17:00", subject_name="Python", teacher_name="Teacher A", subject_id_fk=sb.id)
        db.session.add(lec)
        db.session.commit()

        res = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res["teacher"].name == "Teacher B"
def test_deterministic_tie_breaker(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        schedule_config = ScheduleConfig(inst_code)
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="17:00", end_time="18:00", subject_name="Unknown", teacher_name="Teacher A")
        db.session.add(lec)
        db.session.commit()

        # B and C have same priority, 0 subject familiarity, 0 workload, 0 proxies.
        res1 = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        res2 = find_best_proxy(inst_code, [lec], target_date, "Teacher A", schedule_config)
        assert res1["teacher"].id == res2["teacher"].id

def test_integration_leave_service_flow(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        inst = Institute.query.filter_by(institute_code=inst_code).one()
        c = Course.query.filter_by(institute_code=inst_code).first()
        s = Subject.query.filter_by(institute_code=inst_code).first()
        ta = Teacher.query.filter_by(institute_code=inst_code, teacher_id="TA").one()

        lec1 = Timetable(institute_code=inst_code, institute_id=inst.id, course_id_fk=c.id, teacher_id_fk=ta.id, subject_id_fk=s.id, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="DBMS", teacher_name="Teacher A", session_group_id="G1")
        lec2 = Timetable(institute_code=inst_code, institute_id=inst.id, course_id_fk=c.id, teacher_id_fk=ta.id, subject_id_fk=s.id, class_id="FYCS-A", day_name="Mon", start_time="10:00", end_time="11:00", subject_name="DBMS", teacher_name="Teacher A", session_group_id="G1")
        db.session.add_all([lec1, lec2])
        db.session.commit()

        leave = TeacherLeave(institute_code=inst_code, teacher_id="TA", date=target_date, status="Pending", start_time="09:00")
        db.session.add(leave)
        db.session.commit()

        from utils.leave_service import approve_leave
        success, msg = approve_leave(leave.id)
        assert success

        proxies = Timetable.query.filter_by(institute_code=inst_code, is_proxy=True, specific_date=target_date, session_group_id="G1").all()
        assert len(proxies) == 2
        assert proxies[0].teacher_id_fk == proxies[1].teacher_id_fk
        assert proxies[0].session_group_id == "G1"
        assert proxies[0].teacher_id_fk is not None
        assert proxies[0].subject_id_fk == s.id
        assert proxies[0].institute_id == inst.id
        assert proxies[0].course_id_fk == c.id
        assert proxies[0].leave_id == leave.id

def test_ambiguous_teacher_name_regression(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        # Create duplicate name
        t10 = Teacher(institute_code=inst_code, teacher_id="T10", name="Amit Sharma", email="amit1@t.com", departments="CS", available_days="Mon", max_hours=10)
        t11 = Teacher(institute_code=inst_code, teacher_id="T11", name="Amit Sharma", email="amit2@t.com", departments="CS", available_days="Mon", max_hours=10)
        db.session.add_all([t10, t11])
        db.session.commit()

        # Add legacy timetable row for Amit Sharma
        lec = Timetable(institute_code=inst_code, class_id="FYCS-A", day_name="Mon", start_time="09:00", end_time="10:00", subject_name="DBMS", teacher_name="Amit Sharma")
        db.session.add(lec)
        db.session.commit()

        from utils.helpers import ScheduleConfig
        schedule_config = ScheduleConfig(inst_code)

        # Test resolver explicitly
        from utils.proxy_engine import resolve_legacy_teacher_id
        resolved = resolve_legacy_teacher_id(inst_code, "Amit Sharma")
        assert resolved is None, "Should be ambiguous and fail conservatively"

def test_shared_common_session_integration(app):
    inst_code, target_date = setup_test_data(app)
    with app.app_context():
        inst = Institute.query.filter_by(institute_code=inst_code).one()
        c_a = Course.query.filter_by(institute_code=inst_code, class_id="FYCS-A").one()
        c_b = Course.query.filter_by(institute_code=inst_code, class_id="FYIT-A").one()
        s = Subject.query.filter_by(institute_code=inst_code).first()
        ta = Teacher.query.filter_by(institute_code=inst_code, teacher_id="TA").one()

        lec1 = Timetable(institute_code=inst_code, institute_id=inst.id, course_id_fk=c_a.id, teacher_id_fk=ta.id, subject_id_fk=s.id, class_id="FYCS-A", day_name="Mon", start_time="14:00", end_time="15:00", subject_name="DBMS", teacher_name="Teacher A", session_group_id="COMMON_1")
        lec2 = Timetable(institute_code=inst_code, institute_id=inst.id, course_id_fk=c_b.id, teacher_id_fk=ta.id, subject_id_fk=s.id, class_id="FYIT-A", day_name="Mon", start_time="14:00", end_time="15:00", subject_name="DBMS", teacher_name="Teacher A", session_group_id="COMMON_1")
        db.session.add_all([lec1, lec2])
        db.session.commit()

        leave = TeacherLeave(institute_code=inst_code, teacher_id="TA", date=target_date, status="Pending", start_time="14:00")
        db.session.add(leave)
        db.session.commit()

        from utils.leave_service import approve_leave
        success, msg = approve_leave(leave.id)
        assert success

        proxies = Timetable.query.filter_by(institute_code=inst_code, is_proxy=True, start_time="14:00", specific_date=target_date).all()
        assert len(proxies) == 2
        assert proxies[0].teacher_id_fk == proxies[1].teacher_id_fk
        assert proxies[0].session_group_id == "COMMON_1"
        assert proxies[0].leave_id == leave.id
        assert proxies[1].leave_id == leave.id
        assert proxies[0].institute_id == inst.id
        assert proxies[1].institute_id == inst.id
