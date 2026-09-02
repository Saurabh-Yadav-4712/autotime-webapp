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


def allocate_proxy_for_leave(leave):
    """
    Allocates proxy teachers for a specific approved leave.
    """
    inst_code = leave.institute_code
    target_date = leave.date
    day_name = target_date.strftime("%a")

    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    teachers_by_id = {teacher.teacher_id: teacher for teacher in all_teachers}
    teacher = teachers_by_id.get(leave.teacher_id)
    if not teacher:
        return
    t_name = teacher.name

    # Missed lectures today (Master timetable)
    query = Timetable.query.filter_by(
        institute_code=inst_code, teacher_name=t_name, day_name=day_name, specific_date=None
    )

    if leave.start_time:
        query = query.filter_by(start_time=leave.start_time)

    missed_lectures = query.all()
    if not missed_lectures:
        return

    all_courses = Course.query.filter_by(institute_code=inst_code).all()
    class_dept_map = {c.class_id: c.department for c in all_courses}

    all_subjects = Subject.query.filter_by(institute_code=inst_code).all()
    teacher_classes = {t.name: set() for t in all_teachers}
    teacher_subjects = {t.name: set() for t in all_teachers}
    for sub in all_subjects:
        if sub.teacher_id:
            subject_teacher = teachers_by_id.get(sub.teacher_id)
            if subject_teacher:
                teacher_subjects[subject_teacher.name].add(sub.subject_name)
                for cid in sub.class_id.split(","):
                    teacher_classes[subject_teacher.name].add(cid.strip())

    # Prevent assigning a proxy who is also on leave today
    concurrent_leaves = TeacherLeave.query.filter_by(
        institute_code=inst_code, date=target_date, status="Approved"
    ).all()
    leave_teacher_ids = {l.teacher_id for l in concurrent_leaves}

    relevant_entries = Timetable.query.filter(
        Timetable.institute_code == inst_code,
        Timetable.day_name == day_name,
        (Timetable.specific_date.is_(None)) | (Timetable.specific_date == target_date),
    ).all()
    busy_slots = {(entry.teacher_name, entry.start_time) for entry in relevant_entries}

    for lec in missed_lectures:
        st, et = lec.start_time, lec.end_time
        class_dept = class_dept_map.get(lec.class_id, "")

        available_proxies = []
        for proxy_t in all_teachers:
            if proxy_t.teacher_id in leave_teacher_ids:
                continue

            # Normalize available days
            proxy_days = (
                [d.strip() for d in (proxy_t.available_days or "").split(",")]
                if proxy_t.available_days
                else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            )
            if day_name not in proxy_days:
                continue

            if (proxy_t.name, st) not in busy_slots:
                score = 0
                if lec.subject_name in teacher_subjects.get(proxy_t.name, set()):
                    score += 5
                if lec.class_id in teacher_classes.get(proxy_t.name, set()):
                    score += 3
                if proxy_t.departments == class_dept:
                    score += 1
                available_proxies.append((score, proxy_t))

        if available_proxies:
            available_proxies.sort(key=lambda x: x[0], reverse=True)
            best_proxy = available_proxies[0][1]

            proxy_entry = Timetable(
                institute_code=inst_code,
                class_id=lec.class_id,
                day_name=day_name,
                start_time=st,
                end_time=et,
                subject_name=lec.subject_name,  # Original subject!
                teacher_name=best_proxy.name,
                is_proxy=True,
                specific_date=target_date,
                leave_id=leave.id,  # Traceability
            )
            db.session.add(proxy_entry)
            busy_slots.add((best_proxy.name, st))

            msg = f"PROXY ALERT: You have been assigned a proxy lecture for {lec.subject_name} ({lec.class_id}) on {target_date.strftime('%d %b %Y')} at {st}."
            db.session.add(
                Notification(
                    institute_code=inst_code,
                    user_type="teacher",
                    user_id=best_proxy.teacher_id,
                    message=msg,
                )
            )

            msg_admin = f"Auto-Proxy assigned: {best_proxy.name} will cover {lec.subject_name} for class {lec.class_id} on {target_date.strftime('%d %b %Y')} at {st}."
            db.session.add(
                Notification(institute_code=inst_code, user_type="admin", message=msg_admin)
            )
        else:
            # UNCOVERED LEAVE REPRESENTATION
            proxy_entry = Timetable(
                institute_code=inst_code,
                class_id=lec.class_id,
                day_name=day_name,
                start_time=st,
                end_time=et,
                subject_name=lec.subject_name,
                teacher_name="__UNCOVERED__",  # Specific token for view-model to intercept
                is_proxy=True,
                specific_date=target_date,
                leave_id=leave.id,
            )
            db.session.add(proxy_entry)
            msg_admin = f"Leave Approved, but NO PROXY AVAILABLE for {lec.subject_name} ({lec.class_id}) on {target_date.strftime('%d %b %Y')} at {st}."
            db.session.add(
                Notification(institute_code=inst_code, user_type="admin", message=msg_admin)
            )
