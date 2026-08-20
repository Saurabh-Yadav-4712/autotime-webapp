from models import db, Timetable, Subject, Teacher, Course, Notification, AcademicCalendar, TeacherLeave
from utils.helpers import get_dynamic_time_slots
import random
from datetime import datetime, timedelta

def score_timetable(class_timetable, time_slots):
    score = 0
    # Penalty for gaps
    for c_id, days_data in class_timetable.items():
        for day, slots_data in days_data.items():
            if not slots_data: continue
            filled_indices = [i for i, slot in enumerate(time_slots) if slot[0] in slots_data]
            if filled_indices:
                span = max(filled_indices) - min(filled_indices) + 1
                gaps = span - len(filled_indices)
                score -= (gaps * 5) # heavy penalty for gaps
    return score

def compact_day(class_timetable, teacher_timetable, time_slots, days):
    # Bubble Compaction: Continuously shift lectures and blocks UP into gaps
    made_changes = True
    while made_changes:
        made_changes = False
        for c_id, days_data in class_timetable.items():
            for day in days:
                slots_data = days_data.get(day, {})
                if not slots_data: continue
                
                for i in range(len(time_slots) - 1):
                    slot1 = time_slots[i]
                    slot2 = time_slots[i+1]
                    
                    if slot1[0] not in slots_data and slot2[0] in slots_data:
                        # slot1 is gap, slot2 is filled. Try to pull slot2 up to slot1
                        sub_data = slots_data[slot2[0]]
                        sub = sub_data[0]
                        
                        if ',' in sub.class_id: continue # Do not shift common subjects independently
                        
                        # Check if teacher is free at slot1
                        if slot1[0] not in teacher_timetable.get(sub.teacher_id, {}).get(day, {}):
                            # Identify the full block
                            block_slots = []
                            for j in range(i+1, len(time_slots)):
                                if time_slots[j][0] in slots_data and slots_data[time_slots[j][0]][0].id == sub.id:
                                    block_slots.append(time_slots[j])
                                else:
                                    break
                            
                            # Shift the block up by 1 slot
                            for j, bs in enumerate(block_slots):
                                dest_slot = time_slots[i + j]
                                
                                del class_timetable[c_id][day][bs[0]]
                                del teacher_timetable[sub.teacher_id][day][bs[0]]
                                
                                class_timetable[c_id][day][dest_slot[0]] = (sub, dest_slot[1])
                                teacher_timetable.setdefault(sub.teacher_id, {}).setdefault(day, {})[dest_slot[0]] = (sub, dest_slot[1])
                                
                            made_changes = True
                            break
                if made_changes: break
            if made_changes: break

def engine_generate_timetable(inst_code):
    # Clear master timetable only
    Timetable.query.filter_by(institute_code=inst_code, specific_date=None).delete()
    db.session.commit()
    
    subjects = Subject.query.filter_by(institute_code=inst_code).all()
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    courses = Course.query.filter_by(institute_code=inst_code).all()
    
    teacher_dict = {t.teacher_id: t for t in teachers}
    time_slots = get_dynamic_time_slots(inst_code) 
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    
    common_subjects = []
    normal_subjects = []
    for s in subjects:
        if ',' in s.class_id:
            common_subjects.append(s)
        else:
            normal_subjects.append(s)
            
    # Sort Big-Rocks-First
    normal_subjects.sort(key=lambda x: (-x.session_length, -x.required_hours))
    
    best_timetable = None
    best_teacher_timetable = None
    best_score = -99999
    best_warnings = []
    
    ITERATIONS = 100
    for iteration in range(ITERATIONS):
        class_timetable = {c.class_id: {day: {} for day in days} for c in courses}
        teacher_timetable = {t.teacher_id: {day: {} for day in days} for t in teachers}
        teacher_hours = {t.teacher_id: 0 for t in teachers}
        warnings = []
        
        # Allocate Common Subjects
        for sub in common_subjects:
            assigned_hours = 0
            target_classes = [cid.strip() for cid in sub.class_id.split(',') if cid.strip() in class_timetable]
            if not target_classes: continue
            teacher = teacher_dict.get(sub.teacher_id)
            
            while assigned_hours < sub.required_hours:
                scheduled_this_round = False
                shuffled_days = days.copy()
                random.shuffle(shuffled_days)
                
                for day in shuffled_days:
                    if assigned_hours >= sub.required_hours: break
                    if teacher and day not in teacher.available_days: continue
                    
                    valid_indices = list(range(len(time_slots) - sub.session_length + 1))
                    for idx in valid_indices:
                        slots_to_check = time_slots[idx : idx + sub.session_length]
                        classes_free = all(s[0] not in class_timetable.get(c, {}).get(day, {}) for c in target_classes for s in slots_to_check)
                        teacher_free = all(s[0] not in teacher_timetable.get(sub.teacher_id, {}).get(day, {}) for s in slots_to_check)
                        hours_ok = teacher_hours.get(sub.teacher_id, 0) + sub.session_length <= teacher.max_hours if teacher else True
                        
                        if classes_free and teacher_free and hours_ok:
                            for s in slots_to_check:
                                for c in target_classes:
                                    class_timetable[c][day][s[0]] = (sub, s[1])
                                teacher_timetable.setdefault(sub.teacher_id, {}).setdefault(day, {})[s[0]] = (sub, s[1])
                            
                            if teacher: teacher_hours[sub.teacher_id] += sub.session_length
                            assigned_hours += sub.session_length
                            scheduled_this_round = True
                            break 
                if not scheduled_this_round: 
                    break 

        # Allocate Normal Subjects
        for sub in normal_subjects:
            assigned_hours = 0
            target_class = sub.class_id
            teacher = teacher_dict.get(sub.teacher_id)
            if target_class not in class_timetable: continue
            
            while assigned_hours < sub.required_hours:
                scheduled_this_round = False
                shuffled_days = days.copy()
                random.shuffle(shuffled_days)
                
                for day in shuffled_days:
                    if assigned_hours >= sub.required_hours: break
                    if sub.preferred_days and day not in sub.preferred_days: continue
                    if teacher and day not in teacher.available_days: continue
                    
                    valid_indices = list(range(len(time_slots) - sub.session_length + 1))
                    for idx in valid_indices:
                        slots_to_check = time_slots[idx : idx + sub.session_length]
                        class_free = all(s[0] not in class_timetable[target_class][day] for s in slots_to_check)
                        teacher_free = all(s[0] not in teacher_timetable.get(sub.teacher_id, {}).get(day, {}) for s in slots_to_check)
                        hours_ok = teacher_hours.get(sub.teacher_id, 0) + sub.session_length <= teacher.max_hours if teacher else True
                        
                        if class_free and teacher_free and hours_ok:
                            for s in slots_to_check:
                                class_timetable[target_class][day][s[0]] = (sub, s[1])
                                teacher_timetable.setdefault(sub.teacher_id, {}).setdefault(day, {})[s[0]] = (sub, s[1])
                            
                            if teacher: teacher_hours[sub.teacher_id] += sub.session_length
                            assigned_hours += sub.session_length
                            scheduled_this_round = True
                            break
                if not scheduled_this_round: 
                    warnings.append(f"Unscheduled {sub.required_hours - assigned_hours} hours for {sub.subject_name} ({target_class}). Check teacher max hours or class density.")
                    break
                    
        # Post-Processing
        compact_day(class_timetable, teacher_timetable, time_slots, days)
        
        # Scoring
        score = score_timetable(class_timetable, time_slots)
        if score > best_score:
            best_score = score
            best_timetable = class_timetable
            best_warnings = warnings
            
    # Save Best Timetable with Block Merging
    if best_timetable is None:
        return False, ["Generation failed completely. Please check your data."]
        
    records_to_add = []
    for c_id, days_data in best_timetable.items():
        for day, slots_data in days_data.items():
            # Extract slots and sort by index
            slot_keys = sorted(slots_data.keys(), key=lambda x: [s[0] for s in time_slots].index(x))
            
            i = 0
            while i < len(slot_keys):
                start_time = slot_keys[i]
                sub_data = slots_data[start_time]
                sub = sub_data[0]
                end_time = sub_data[1]
                
                # Look ahead for merging blocks of the same subject
                j = i + 1
                while j < len(slot_keys):
                    next_time = slot_keys[j]
                    next_sub_data = slots_data[next_time]
                    # Ensure they are consecutive
                    curr_idx = [s[0] for s in time_slots].index(slot_keys[j-1])
                    next_idx = [s[0] for s in time_slots].index(next_time)
                    if next_sub_data[0].subject_code == sub.subject_code and next_idx == curr_idx + 1:
                        end_time = next_sub_data[1] # Extend block
                        j += 1
                    else:
                        break
                
                teacher = teacher_dict.get(sub.teacher_id)
                t_name = teacher.name if teacher else sub.teacher_id
                
                new_entry = Timetable(
                    institute_code=inst_code,
                    class_id=c_id,
                    day_name=day,
                    start_time=start_time,
                    end_time=end_time,
                    subject_name=sub.subject_name,
                    teacher_name=t_name,
                    is_proxy=False
                )
                records_to_add.append(new_entry)
                i = j # Skip merged slots

    db.session.bulk_save_objects(records_to_add)
    db.session.commit()
    return True, best_warnings

def auto_allocate_proxy(inst_code, target_date):
    # Determine the day of the week for the target_date
    day_name = target_date.strftime('%a')
    
    # Check for Teacher Leaves on this date
    leaves = TeacherLeave.query.filter_by(institute_code=inst_code, date=target_date, status='Approved').all()
    leave_teacher_ids = [l.teacher_id for l in leaves]
    if not leave_teacher_ids: return # Nothing to proxy
    
    time_slots = get_dynamic_time_slots(inst_code)
    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    
    for t_id in leave_teacher_ids:
        teacher = Teacher.query.filter_by(institute_code=inst_code, teacher_id=t_id).first()
        t_name = teacher.name if teacher else t_id
        
        # Find all lectures this teacher was supposed to take today (from master timetable)
        missed_lectures = Timetable.query.filter_by(
            institute_code=inst_code, 
            teacher_name=t_name, 
            day_name=day_name,
            specific_date=None
        ).all()
        
        for lec in missed_lectures:
            # We need to find a mutual gap (class free + another teacher free) for THIS lecture
            # Let's search the next 7 days
            assigned = False
            for offset in range(1, 8):
                search_date = target_date + timedelta(days=offset)
                search_day = search_date.strftime('%a')
                
                if search_day == 'Sun': continue
                
                # Fetch class timetable for search_date (including overrides)
                # To simplify, we just check the master timetable for the class on that day
                class_master = Timetable.query.filter_by(institute_code=inst_code, class_id=lec.class_id, day_name=search_day, specific_date=None).all()
                class_busy_slots = {c.start_time for c in class_master}
                
                for slot in time_slots:
                    st, et = slot[0], slot[1]
                    if st not in class_busy_slots:
                        # Class is free. Can we find ANY teacher from the same department?
                        sub = Subject.query.filter_by(institute_code=inst_code, subject_name=lec.subject_name).first()
                        dept = Course.query.filter_by(institute_code=inst_code, class_id=lec.class_id).first().department
                        
                        # Find a teacher who is available
                        for proxy_t in all_teachers:
                            if proxy_t.teacher_id == t_id or search_day not in proxy_t.available_days: continue
                            
                            proxy_master = Timetable.query.filter_by(institute_code=inst_code, teacher_name=proxy_t.name, day_name=search_day, specific_date=None).all()
                            if not any(pm.start_time == st for pm in proxy_master):
                                # Found a gap! Assign proxy
                                proxy_entry = Timetable(
                                    institute_code=inst_code,
                                    class_id=lec.class_id,
                                    day_name=search_day,
                                    start_time=st,
                                    end_time=et,
                                    subject_name=lec.subject_name,
                                    teacher_name=proxy_t.name,
                                    is_proxy=True,
                                    specific_date=search_date
                                )
                                db.session.add(proxy_entry)
                                
                                # Send Notification to Proxy Teacher
                                msg = f"You have been assigned a proxy lecture for {lec.subject_name} ({lec.class_id}) on {search_date.strftime('%d %b %Y')} at {st}."
                                notif = Notification(institute_code=inst_code, user_type='teacher', user_id=proxy_t.teacher_id, message=msg)
                                db.session.add(notif)
                                
                                # Notification to Admin
                                msg_admin = f"Auto-Proxy assigned: {proxy_t.name} will cover {lec.subject_name} for class {lec.class_id} on {search_date.strftime('%d %b %Y')}."
                                notif_admin = Notification(institute_code=inst_code, user_type='admin', message=msg_admin)
                                db.session.add(notif_admin)
                                
                                assigned = True
                                break
                        if assigned: break
                if assigned: break
                
    db.session.commit()
