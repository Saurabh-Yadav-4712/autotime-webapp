import datetime
from collections import defaultdict
from models import Teacher, Timetable, Course, TeacherLeave, Subject

def normalize_department(dept_str):
    if not dept_str:
        return ""
    return dept_str.strip().upper()

def get_week_bounds(target_date):
    start = target_date - datetime.timedelta(days=target_date.weekday())
    end = start + datetime.timedelta(days=6)
    return start, end

def resolve_legacy_teacher_id(institute_code, teacher_name, teachers_by_id=None):
    if not teacher_name or teacher_name == "__UNCOVERED__":
        return None

    if teachers_by_id is None:
        all_teachers = Teacher.query.filter_by(institute_code=institute_code).all()
    else:
        all_teachers = teachers_by_id.values()

    matches = [t for t in all_teachers if t.name == teacher_name]
    if len(matches) == 1:
        return matches[0].id
    # If 0 matches or >1 match (ambiguous), return None conservatively
    return None

def get_teacher_workloads(institute_code, target_date, teachers_by_id):
    """
    Returns a dict of teacher_id -> effective weekly workload for the target_date's week.
    Workload = count of logical master sessions + logical proxy sessions in that week.
    """
    week_start, week_end = get_week_bounds(target_date)

    entries = Timetable.query.filter_by(institute_code=institute_code).all()
    workload = defaultdict(int)
    seen = set()

    for e in entries:
        if e.teacher_name == "__UNCOVERED__":
            continue

        tid = e.teacher_id_fk
        # Legacy fallback
        if not tid:
            tid = resolve_legacy_teacher_id(institute_code, e.teacher_name, teachers_by_id)

        if not tid:
            continue

        if e.specific_date is None:
            # Master timetable counts for every week
            key = (tid, e.day_name, e.start_time, "master")
            if key not in seen:
                seen.add(key)
                workload[tid] += 1
        else:
            # Date-specific proxy
            if week_start <= e.specific_date <= week_end:
                key = (tid, e.specific_date, e.start_time, "proxy")
                if key not in seen:
                    seen.add(key)
                    workload[tid] += 1
    return workload

def get_proxy_assignments_count(institute_code, target_date, teachers_by_id):
    """
    Returns dict of teacher_id -> total proxy assignments in the target week.
    """
    week_start, week_end = get_week_bounds(target_date)
    entries = Timetable.query.filter(
        Timetable.institute_code == institute_code,
        Timetable.is_proxy == True,
        Timetable.specific_date >= week_start,
        Timetable.specific_date <= week_end
    ).all()

    proxy_counts = defaultdict(int)
    seen = set()
    for e in entries:
        if e.teacher_name == "__UNCOVERED__":
            continue

        tid = e.teacher_id_fk
        # Legacy fallback
        if not tid:
            tid = resolve_legacy_teacher_id(institute_code, e.teacher_name, teachers_by_id)

        if not tid:
            continue

        key = (tid, e.specific_date, e.start_time)
        if key not in seen:
            seen.add(key)
            proxy_counts[tid] += 1
    return proxy_counts

def find_best_proxy(institute_code, affected_session_block, target_date, absent_teacher_id, schedule_config):
    if not affected_session_block:
        return {
            "teacher": None,
            "priority": None,
            "reason": "INVALID_SESSION_BLOCK"
        }

    all_teachers = Teacher.query.filter_by(institute_code=institute_code).all()
    teachers_by_id = {t.id: t for t in all_teachers}

    all_courses = Course.query.filter_by(institute_code=institute_code).all()
    class_dept_map = {c.class_id: c.department for c in all_courses}

    all_subjects = Subject.query.filter_by(institute_code=institute_code).all()

    teacher_classes = defaultdict(set)
    teacher_subjects = defaultdict(set)
    teacher_subject_codes = defaultdict(set)
    for sub in all_subjects:
        if sub.teacher_id:
            sub_t = None
            for t in all_teachers:
                if t.teacher_id == sub.teacher_id:
                    sub_t = t
                    break
            if sub_t:
                teacher_subjects[sub_t.id].add(sub.id)
                teacher_subject_codes[sub_t.id].add(sub.subject_code)
                for cid in sub.class_id.split(","):
                    teacher_classes[sub_t.id].add(cid.strip())

    day_name = target_date.strftime("%a")

    concurrent_leaves = TeacherLeave.query.filter_by(
        institute_code=institute_code, date=target_date, status="Approved"
    ).all()
    leave_teacher_ids = set()
    for l in concurrent_leaves:
        # l.teacher_id is string teacher_id, convert to PK id
        for t in all_teachers:
            if t.teacher_id == l.teacher_id:
                leave_teacher_ids.add(t.id)
                break

    relevant_entries = Timetable.query.filter(
        Timetable.institute_code == institute_code,
        Timetable.day_name == day_name,
        (Timetable.specific_date.is_(None)) | (Timetable.specific_date == target_date),
    ).all()

    busy_slots = set()
    for entry in relevant_entries:
        if entry.teacher_name == "__UNCOVERED__":
            continue
        tid = entry.teacher_id_fk
        if not tid:
            tid = resolve_legacy_teacher_id(institute_code, entry.teacher_name, teachers_by_id)
        if tid:
            busy_slots.add((tid, entry.start_time))

    required_start_times = {l.start_time for l in affected_session_block}
    first_lec = affected_session_block[0]

    target_classes = {l.class_id for l in affected_session_block}

    # Target Dept logic
    target_dept_raw = class_dept_map.get(first_lec.class_id, "")
    target_dept_norm = normalize_department(target_dept_raw)

    target_subject_id = first_lec.subject_id_fk
    target_subject_code = None
    if not target_subject_id:
        for sub in all_subjects:
            if sub.subject_name == first_lec.subject_name and first_lec.class_id in [c.strip() for c in sub.class_id.split(",")]:
                target_subject_code = sub.subject_code
                break

    workloads = get_teacher_workloads(institute_code, target_date, teachers_by_id)
    proxy_counts = get_proxy_assignments_count(institute_code, target_date, teachers_by_id)

    candidates = []

    for proxy_t in all_teachers:
        if proxy_t.id == absent_teacher_id:
            continue
        if proxy_t.id in leave_teacher_ids:
            continue

        proxy_days = (
            [d.strip() for d in (proxy_t.available_days or "").split(",")]
            if proxy_t.available_days
            else schedule_config.working_days
        )
        if day_name not in proxy_days:
            continue

        is_free = all((proxy_t.id, st) not in busy_slots for st in required_start_times)
        if not is_free:
            continue

        block_length = len(required_start_times)
        if workloads[proxy_t.id] + block_length > proxy_t.max_hours:
            continue

        # Department matching
        teacher_depts = {normalize_department(x) for x in (proxy_t.departments or "").split(",")}

        teaches_same_class = any(cls in teacher_classes[proxy_t.id] for cls in target_classes)
        if teaches_same_class:
            priority = 1
        elif target_dept_norm in teacher_depts:
            priority = 2
        else:
            priority = 3

        # Same subject by ID or legacy code
        if target_subject_id:
            same_subject = 1 if target_subject_id in teacher_subjects[proxy_t.id] else 0
        else:
            same_subject = 1 if target_subject_code and target_subject_code in teacher_subject_codes[proxy_t.id] else 0

        wload = workloads[proxy_t.id]
        pcount = proxy_counts[proxy_t.id]
        stable_id = proxy_t.id

        candidates.append({
            "teacher": proxy_t,
            "priority": priority,
            "same_subject": same_subject,
            "workload": wload,
            "proxy_count": pcount,
            "stable_id": stable_id
        })

    if not candidates:
        return {
            "teacher": None,
            "priority": None,
            "reason": "NO_ELIGIBLE_PROXY"
        }

    candidates.sort(key=lambda x: (
        x["priority"],
        -x["same_subject"],
        x["workload"],
        x["proxy_count"],
        x["stable_id"]
    ))

    best = candidates[0]

    return {
        "teacher": best["teacher"],
        "priority": "SAME_CLASS" if best["priority"] == 1 else ("SAME_DEPARTMENT" if best["priority"] == 2 else "OTHER_DEPARTMENT"),
        "cross_department": best["priority"] == 3,
        "reason": "Priority selected"
    }

