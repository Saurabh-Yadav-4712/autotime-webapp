from models import db, Timetable, Subject, Teacher, Course, Notification, AcademicCalendar, TeacherLeave
from utils.helpers import get_dynamic_time_slots
import random
from datetime import datetime, timedelta

def score_timetable(class_timetable, time_slots):
    score = 0
    for c_id, days_data in class_timetable.items():
        daily_counts = []
        for day, slots in days_data.items():
            count = len(slots)
            daily_counts.append(count)
            if not slots: continue
            
            # Find min and max index
            indices = [[s[0] for s in time_slots].index(k) for k in slots.keys()]
            if indices:
                span = max(indices) - min(indices) + 1
                gaps = span - len(indices)
                score -= (gaps * 50) # Extremely heavy penalty for mid-day gaps
        
        # Penalize uneven distribution of lectures across days
        if daily_counts:
            avg = sum(daily_counts) / len(daily_counts)
            variance = sum((x - avg) ** 2 for x in daily_counts)
            score -= variance
            
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
            
    best_timetable = None
    best_teacher_timetable = None
    best_score = -99999
    best_warnings = []
    
    ITERATIONS = 500
    for iteration in range(ITERATIONS):
        # Shuffle subjects to explore different placement orders, then stable sort
        import random
        random.shuffle(normal_subjects)
        normal_subjects.sort(key=lambda x: (-x.session_length, -x.required_hours))
        
        random.shuffle(common_subjects)
        common_subjects.sort(key=lambda x: (-x.session_length, -x.required_hours))
        
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
                
                disp_name = f"{sub.subject_name} (Practical)" if sub.subject_type and sub.subject_type.lower() == 'practical' else sub.subject_name
                
                new_entry = Timetable(
                    institute_code=inst_code,
                    class_id=c_id,
                    day_name=day,
                    start_time=start_time,
                    end_time=end_time,
                    subject_name=disp_name,
                    teacher_name=t_name,
                    is_proxy=False
                )
                records_to_add.append(new_entry)
                i = j # Skip merged slots

    db.session.bulk_save_objects(records_to_add)
    db.session.commit()
    return True, best_warnings

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
