from models import db, Timetable, Subject, Teacher, Course, Notification, AcademicCalendar, TeacherLeave, GenerationHistory, Institute
from utils.helpers import get_dynamic_time_slots
import random
from datetime import datetime, timedelta

def engine_generate_timetable(inst_code):
    from models import Timetable, Subject, Teacher, Course, db, GenerationHistory, Institute
    from utils.helpers import get_dynamic_time_slots
    from utils.scheduler import TimeSlot, SessionOccurrence, GlobalState, TimetableEngine, TimetableValidator
    import random
    import json
    # Defer deletion of the existing timetable until successful generation
    # to maintain database transaction safety.

    institute = Institute.query.filter_by(institute_code=inst_code).first()
    institute_id = institute.id if institute else 0

    subjects = Subject.query.filter_by(institute_code=inst_code).all()
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    courses = Course.query.filter_by(institute_code=inst_code).all()

    teacher_dict = {t.teacher_id: t for t in teachers}
    raw_slots = get_dynamic_time_slots(inst_code)
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

    time_slots = []
    for idx, (st, et) in enumerate(raw_slots):
        time_slots.append(TimeSlot(day="", idx=idx, start_time=st, end_time=et))

    state = GlobalState()
    for t in teachers:
        state.teacher_max_hours[t.teacher_id] = t.max_hours

    units = []

    for sub in subjects:
        # Determine target classes
        if ',' in sub.class_id:
            target_classes = [c.strip() for c in sub.class_id.split(',') if c.strip()]
        else:
            target_classes = [sub.class_id.strip()]

        t_id = sub.teacher_id if sub.teacher_id else ""

        pref_days = []
        if sub.preferred_days:
            pref_days = [d.strip() for d in sub.preferred_days.split(',') if d.strip()]

        is_prac = sub.subject_type and sub.subject_type.lower() == 'practical'

        # Determine how many sessions to create based on required_hours and session_length
        session_len = sub.session_length if sub.session_length else 1
        num_sessions = sub.required_hours // session_len

        for i in range(num_sessions):
            unit = SessionOccurrence(
                id=f"{sub.id}_{i}",
                subject_id=sub.id,
                subject_name=sub.subject_name,
                teacher_id=t_id,
                target_classes=target_classes,
                duration=session_len,
                preferred_days=pref_days,
                is_practical=is_prac
            )
            units.append(unit)

    engine = TimetableEngine(time_slots=time_slots, days=days)
    success, scheduled_units, msg, stats, diag = engine.generate(units, state)

    if success:
        # Validate
        is_valid, errors = TimetableValidator.audit(scheduled_units, time_slots)
        if not is_valid:
            success = False
            msg = f"Validation failed: {errors[0]}"
            from utils.scheduler.diagnostics import GenerationDiagnostics
            diag = GenerationDiagnostics(
                status="FAILED",
                reason_code="VALIDATION_FAILED",
                primary_bottleneck=msg
            )

    if success:
        # Transaction Safety: Delete old timetable only when replacement is ready
        Timetable.query.filter_by(institute_code=inst_code, specific_date=None).delete()

        records_to_add = []
        for unit in scheduled_units:
            disp_name = f"{unit.subject_name} (Practical)" if unit.is_practical else unit.subject_name
            teacher = teacher_dict.get(unit.teacher_id)
            t_name = teacher.name if teacher else unit.teacher_id
            t_id_fk = teacher.id if teacher else None
            s_id_fk = getattr(unit, 'subject_id', None)

            for c_id in unit.target_classes:
                course_match = next((c for c in courses if getattr(c, 'class_id', None) == c_id), None)
                c_id_fk = course_match.id if course_match else None

                for offset in range(unit.duration):
                    actual_slot = time_slots[unit.assigned_slot.idx + offset]
                    new_entry = Timetable(
                        institute_id=institute_id,
                        institute_code=inst_code,
                        course_id_fk=c_id_fk,
                        teacher_id_fk=t_id_fk,
                        subject_id_fk=s_id_fk,
                        session_group_id=unit.id,
                        class_id=c_id,
                        day_name=actual_slot.day,
                        start_time=actual_slot.start_time,
                        end_time=actual_slot.end_time,
                        subject_name=disp_name,
                        teacher_name=t_name,
                        is_proxy=False
                    )
                    records_to_add.append(new_entry)

        db.session.bulk_save_objects(records_to_add)

    # Record to GenerationHistory
    gap_score = stats.get("gap_penalty") if success else None
    history = GenerationHistory(
        institute_id=institute_id,
        institute_code=inst_code,
        status="SUCCESS" if success else "FAILED",
        sessions_count=len(scheduled_units) if scheduled_units else 0,
        generation_time=stats.get("feasibility_time", 0),
        optimization_time=stats.get("optimization_time", 0),
        gap_score=gap_score,
        primary_failure_reason=diag.primary_bottleneck if diag else None,
        diagnostics_json=json.dumps(diag.to_dict()) if diag else None
    )
    db.session.add(history)
    db.session.commit()

    if success:
        stats["logical_session_occurrences"] = len(scheduled_units)
        stats["occupied_class_periods"] = sum(unit.duration * len(unit.target_classes) for unit in scheduled_units)
    else:
        stats["logical_session_occurrences"] = 0
        stats["occupied_class_periods"] = 0

    result = {
        "success": success,
        "status": "SUCCESS" if success else "FAILED",
        "message": msg,
        "stats": stats,
        "diagnostics": diag.to_dict() if diag else None
    }

    return result

def auto_allocate_proxy(inst_code, target_date):
    day_name = target_date.strftime('%a')

    # Check for Teacher Leaves on this date
    leaves = TeacherLeave.query.filter_by(institute_code=inst_code, date=target_date, status='Approved').all()
    leave_teacher_ids = [l.teacher_id for l in leaves]
    if not leave_teacher_ids: return

    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    # Cache class to dept mapping
    all_courses = Course.query.filter_by(institute_code=inst_code).all()
    class_dept_map = {c.class_id: c.department for c in all_courses}

    # Cache subject mappings
    all_subjects = Subject.query.filter_by(institute_code=inst_code).all()
    teacher_classes = {t.name: set() for t in all_teachers}
    teacher_subjects = {t.name: set() for t in all_teachers}
    for sub in all_subjects:
        if sub.teacher_id:
            teacher_name = next((t.name for t in all_teachers if t.teacher_id == sub.teacher_id), None)
            if teacher_name:
                teacher_subjects[teacher_name].add(sub.subject_name)
                for cid in sub.class_id.split(','):
                    teacher_classes[teacher_name].add(cid.strip())

    for t_id in leave_teacher_ids:
        teacher = next((t for t in all_teachers if t.teacher_id == t_id), None)
        if not teacher: continue
        t_name = teacher.name

        # Missed lectures today
        missed_lectures = Timetable.query.filter_by(
            institute_code=inst_code,
            teacher_name=t_name,
            day_name=day_name,
            specific_date=None
        ).all()

        for lec in missed_lectures:
            st, et = lec.start_time, lec.end_time
            class_dept = class_dept_map.get(lec.class_id, "")

            # Find free teachers at this exact time slot today
            available_proxies = []
            for proxy_t in all_teachers:
                if proxy_t.teacher_id in leave_teacher_ids: continue
                if day_name not in proxy_t.available_days: continue

                # Check if proxy_t is busy at this slot
                # (Check master timetable AND existing proxy assignments for today)
                is_busy = Timetable.query.filter_by(institute_code=inst_code, teacher_name=proxy_t.name, day_name=day_name, start_time=st).filter((Timetable.specific_date == None) | (Timetable.specific_date == target_date)).first()

                if not is_busy:
                    # Calculate priority score
                    score = 0
                    if lec.subject_name in teacher_subjects.get(proxy_t.name, set()):
                        score += 5 # Teaches same subject
                    if lec.class_id in teacher_classes.get(proxy_t.name, set()):
                        score += 3 # Teaches same class
                    if proxy_t.departments == class_dept:
                        score += 1 # Same department

                    available_proxies.append((score, proxy_t))

            if available_proxies:
                # Sort by score descending
                available_proxies.sort(key=lambda x: x[0], reverse=True)
                best_proxy = available_proxies[0][1]

                proxy_entry = Timetable(
                    institute_code=inst_code,
                    class_id=lec.class_id,
                    day_name=day_name,
                    start_time=st,
                    end_time=et,
                    subject_name=lec.subject_name,
                    teacher_name=best_proxy.name,
                    is_proxy=True,
                    specific_date=target_date
                )
                db.session.add(proxy_entry)

                msg = f"PROXY ALERT: You have been assigned a proxy lecture for {lec.subject_name} ({lec.class_id}) on {target_date.strftime('%d %b %Y')} at {st}."
                db.session.add(Notification(institute_code=inst_code, user_type='teacher', user_id=best_proxy.teacher_id, message=msg))

                msg_admin = f"Auto-Proxy assigned: {best_proxy.name} will cover {lec.subject_name} for class {lec.class_id} on {target_date.strftime('%d %b %Y')} at {st}."
                db.session.add(Notification(institute_code=inst_code, user_type='admin', message=msg_admin))

    db.session.commit()
