from models import db, TeacherLeave, Timetable, Teacher, Course, Subject, Notification
from datetime import datetime
from zoneinfo import ZoneInfo


def get_local_date():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def approve_leave(leave_id, institute_code=None):
    """
    Approves a pending leave and triggers proxy allocation.
    Returns (success: bool, message: str)
    """
    query = TeacherLeave.query.filter_by(id=leave_id)
    if institute_code:
        query = query.filter_by(institute_code=institute_code)
    leave = query.first()
    if not leave:
        return False, "Leave request not found."

    if leave.status != "Pending":
        return False, f"Cannot approve leave. Current status is {leave.status}."

    try:
        leave.status = "Approved"
        allocate_proxy_for_leave(leave)
        db.session.commit()
        return True, "Leave approved and proxies allocated successfully."
    except Exception:
        db.session.rollback()
        return False, "Unable to approve the leave. No changes were saved."


def cancel_leave(leave_id, actor_name, institute_code=None, teacher_id=None):
    """
    Cancels a Pending or Approved future leave.
    Returns (success: bool, message: str)
    """
    query = TeacherLeave.query.filter_by(id=leave_id)
    if institute_code:
        query = query.filter_by(institute_code=institute_code)
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    leave = query.first()
    if not leave:
        return False, "Leave request not found."

    if leave.status not in ["Pending", "Approved"]:
        return False, f"Cannot cancel leave with status {leave.status}."

    local_date = get_local_date()
    if leave.date <= local_date and leave.status == "Approved":
        return False, "Cannot cancel an approved leave for today or a past date."

    # Transactional cleanup
    try:
        if leave.status == "Approved":
            # Find and notify proxies before deletion
            proxies = Timetable.query.filter_by(leave_id=leave.id).all()
            for proxy in proxies:
                proxy_teacher = Teacher.query.filter_by(
                    institute_code=proxy.institute_code, name=proxy.teacher_name
                ).first()
                if proxy_teacher:
                    msg = f"CANCELLATION: Your proxy assignment for {proxy.subject_name} on {proxy.specific_date} has been cancelled."
                    db.session.add(
                        Notification(
                            institute_code=proxy.institute_code,
                            user_type="teacher",
                            user_id=proxy_teacher.teacher_id,
                            message=msg,
                        )
                    )

            # Delete ONLY the proxy overrides specifically tied to this leave
            Timetable.query.filter_by(leave_id=leave.id).delete()

        leave.status = "Cancelled"

        # Notify admin
        teacher = Teacher.query.filter_by(
            teacher_id=leave.teacher_id, institute_code=leave.institute_code
        ).first()
        t_name = teacher.name if teacher else leave.teacher_id
        admin_msg = f"{actor_name} cancelled the leave request for {t_name} on {leave.date.strftime('%d %b %Y')}."
        db.session.add(
            Notification(institute_code=leave.institute_code, user_type="admin", message=admin_msg)
        )

        db.session.commit()
        return True, "Leave cancelled successfully."
    except Exception:
        db.session.rollback()
        return False, "Unable to cancel the leave. No changes were saved."


from utils.helpers import ScheduleConfig

def allocate_proxy_for_leave(leave):
    from utils.proxy_engine import find_best_proxy
    from utils.helpers import ScheduleConfig
    from models import Teacher, Timetable, Course, Subject, TeacherLeave, Notification, db

    schedule_config = ScheduleConfig(leave.institute_code)
    inst_code = leave.institute_code
    target_date = leave.date
    day_name = target_date.strftime("%a")

    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    teachers_by_id = {teacher.teacher_id: teacher for teacher in all_teachers}
    teacher = teachers_by_id.get(leave.teacher_id)
    if not teacher:
        return
    t_name = teacher.name
    absent_teacher_id = teacher.id


    query = Timetable.query.filter_by(
        institute_code=inst_code, teacher_name=t_name, day_name=day_name, specific_date=None
    )
    all_day_lectures = query.all()

    if leave.start_time:
        target_lec = next((l for l in all_day_lectures if l.start_time == leave.start_time), None)
        if not target_lec:
            return

        if target_lec.session_group_id:
            missed_lectures = [l for l in all_day_lectures if l.session_group_id == target_lec.session_group_id]
        else:
            missed_lectures = [target_lec]
    else:
        missed_lectures = all_day_lectures

    if not missed_lectures:
        return


    blocks = {}
    for lec in missed_lectures:
        if lec.session_group_id:
            key = f"group_{lec.session_group_id}"
        else:
            key = f"single_{lec.start_time}_{lec.subject_name}"
        blocks.setdefault(key, []).append(lec)

    for key, block in blocks.items():
        proxy_result = find_best_proxy(inst_code, block, target_date, absent_teacher_id, schedule_config)
        best_proxy = proxy_result.get("teacher")

        if best_proxy:
            for lec in block:
                proxy_entry = Timetable(
                    institute_code=inst_code,
                    institute_id=lec.institute_id,
                    course_id_fk=lec.course_id_fk,
                    teacher_id_fk=best_proxy.id,
                    subject_id_fk=lec.subject_id_fk,
                    class_id=lec.class_id,
                    day_name=day_name,
                    start_time=lec.start_time,
                    end_time=lec.end_time,
                    subject_name=lec.subject_name,
                    teacher_name=best_proxy.name,
                    session_group_id=lec.session_group_id,
                    is_proxy=True,
                    specific_date=target_date,
                    leave_id=leave.id,
                )
                db.session.add(proxy_entry)

            msg = f"PROXY ALERT: You have been assigned a proxy lecture for {block[0].subject_name} ({block[0].class_id}) on {target_date.strftime('%d %b %Y')} at {block[0].start_time}."
            db.session.add(
                Notification(
                    institute_code=inst_code,
                    user_type="teacher",
                    user_id=best_proxy.teacher_id,
                    message=msg,
                )
            )
        else:
            for lec in block:
                proxy_entry = Timetable(
                    institute_code=inst_code,
                    institute_id=lec.institute_id,
                    course_id_fk=lec.course_id_fk,
                    teacher_id_fk=None,
                    subject_id_fk=lec.subject_id_fk,
                    class_id=lec.class_id,
                    day_name=day_name,
                    start_time=lec.start_time,
                    end_time=lec.end_time,
                    subject_name=lec.subject_name,
                    teacher_name="__UNCOVERED__",
                    session_group_id=lec.session_group_id,
                    is_proxy=True,
                    specific_date=target_date,
                    leave_id=leave.id,
                )
                db.session.add(proxy_entry)


def cancel_leave(leave_id, actor_name, institute_code=None, teacher_id=None):
    """
    Cancels a Pending or Approved future leave.
    Returns (success: bool, message: str)
    """
    query = TeacherLeave.query.filter_by(id=leave_id)
    if institute_code:
        query = query.filter_by(institute_code=institute_code)
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    leave = query.first()
    if not leave:
        return False, "Leave request not found."

    if leave.status not in ["Pending", "Approved"]:
        return False, f"Cannot cancel leave with status {leave.status}."

    local_date = get_local_date()
    if leave.date <= local_date and leave.status == "Approved":
        return False, "Cannot cancel an approved leave for today or a past date."

    # Transactional cleanup
    try:
        if leave.status == "Approved":
            # Find and notify proxies before deletion
            proxies = Timetable.query.filter_by(leave_id=leave.id).all()
            for proxy in proxies:
                proxy_teacher = Teacher.query.filter_by(
                    institute_code=proxy.institute_code, name=proxy.teacher_name
                ).first()
                if proxy_teacher:
                    msg = f"CANCELLATION: Your proxy assignment for {proxy.subject_name} on {proxy.specific_date} has been cancelled."
                    db.session.add(
                        Notification(
                            institute_code=proxy.institute_code,
                            user_type="teacher",
                            user_id=proxy_teacher.teacher_id,
                            message=msg,
                        )
                    )

            # Delete ONLY the proxy overrides specifically tied to this leave
            Timetable.query.filter_by(leave_id=leave.id).delete()

        leave.status = "Cancelled"

        # Notify admin
        teacher = Teacher.query.filter_by(
            teacher_id=leave.teacher_id, institute_code=leave.institute_code
        ).first()
        t_name = teacher.name if teacher else leave.teacher_id
        admin_msg = f"{actor_name} cancelled the leave request for {t_name} on {leave.date.strftime('%d %b %Y')}."
        db.session.add(
            Notification(institute_code=leave.institute_code, user_type="admin", message=admin_msg)
        )

        db.session.commit()
        return True, "Leave cancelled successfully."
    except Exception:
        db.session.rollback()
        return False, "Unable to cancel the leave. No changes were saved."


from utils.helpers import ScheduleConfig

def allocate_proxy_for_leave(leave):
    from utils.proxy_engine import find_best_proxy
    from utils.helpers import ScheduleConfig
    from models import Teacher, Timetable, Course, Subject, TeacherLeave, Notification, db

    schedule_config = ScheduleConfig(leave.institute_code)
    inst_code = leave.institute_code
    target_date = leave.date
    day_name = target_date.strftime("%a")

    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    teachers_by_id = {teacher.teacher_id: teacher for teacher in all_teachers}
    teacher = teachers_by_id.get(leave.teacher_id)
    if not teacher:
        return
    t_name = teacher.name
    absent_teacher_id = teacher.id

    query = Timetable.query.filter_by(
        institute_code=inst_code, teacher_name=t_name, day_name=day_name, specific_date=None
    )
    all_day_lectures = query.all()

    if leave.start_time:
        # Find the specific lecture
        target_lec = next((l for l in all_day_lectures if l.start_time == leave.start_time), None)
        if not target_lec:
            return

        if target_lec.session_group_id:
            missed_lectures = [l for l in all_day_lectures if l.session_group_id == target_lec.session_group_id]
        else:
            missed_lectures = [target_lec]
    else:
        missed_lectures = all_day_lectures

    if not missed_lectures:
        return

    blocks = {}
    for lec in missed_lectures:
        if lec.session_group_id:
            key = f"group_{lec.session_group_id}"
        else:
            key = f"single_{lec.start_time}_{lec.subject_name}"
        blocks.setdefault(key, []).append(lec)

    for key, block in blocks.items():
        proxy_result = find_best_proxy(inst_code, block, target_date, absent_teacher_id, schedule_config)
        best_proxy = proxy_result.get("teacher")

        if best_proxy:
            for lec in block:
                proxy_entry = Timetable(
                    institute_code=inst_code,
                    institute_id=lec.institute_id,
                    course_id_fk=lec.course_id_fk,
                    teacher_id_fk=best_proxy.id,
                    subject_id_fk=lec.subject_id_fk,
                    class_id=lec.class_id,
                    day_name=day_name,
                    start_time=lec.start_time,
                    end_time=lec.end_time,
                    subject_name=lec.subject_name,
                    teacher_name=best_proxy.name,
                    session_group_id=lec.session_group_id,
                    is_proxy=True,
                    specific_date=target_date,
                    leave_id=leave.id,
                )
                db.session.add(proxy_entry)

            msg = f"PROXY ALERT: You have been assigned a proxy lecture for {block[0].subject_name} ({block[0].class_id}) on {target_date.strftime('%d %b %Y')} at {block[0].start_time}."
            db.session.add(
                Notification(
                    institute_code=inst_code,
                    user_type="teacher",
                    user_id=best_proxy.teacher_id,
                    message=msg,
                )
            )
        else:
            for lec in block:
                proxy_entry = Timetable(
                    institute_code=inst_code,
                    institute_id=lec.institute_id,
                    course_id_fk=lec.course_id_fk,
                    teacher_id_fk=None,
                    subject_id_fk=lec.subject_id_fk,
                    class_id=lec.class_id,
                    day_name=day_name,
                    start_time=lec.start_time,
                    end_time=lec.end_time,
                    subject_name=lec.subject_name,
                    teacher_name="__UNCOVERED__",
                    session_group_id=lec.session_group_id,
                    is_proxy=True,
                    specific_date=target_date,
                    leave_id=leave.id,
                )
                db.session.add(proxy_entry)
