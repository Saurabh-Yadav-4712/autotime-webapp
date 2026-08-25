import sys
import os
import time
import uuid

sys.path.append(os.path.abspath('.'))
from app import create_app
from models import db, Institute, Teacher, Course, Subject, Settings, Timetable, SubjectCourse

class MigrationIntegrityError(Exception): pass

def run_migration():
    institutes = Institute.query.all()
    inst_map = {inst.institute_code: inst.id for inst in institutes}
    
    for TeacherModel in [Teacher, Course, Subject, Timetable, Settings]:
        records = TeacherModel.query.all()
        for r in records:
            if not getattr(r, 'institute_code', None): continue
            if r.institute_code not in inst_map:
                raise MigrationIntegrityError(f"Unknown institute_code {r.institute_code} on {TeacherModel.__name__} ID {r.id}")
            r.institute_id = inst_map[r.institute_code]
    db.session.flush()

    teachers = Teacher.query.all()
    teacher_map = {(t.institute_id, t.teacher_id): t.id for t in teachers}
    
    teacher_name_map = {}
    for t in teachers:
        key = (t.institute_id, t.name)
        if key not in teacher_name_map:
            teacher_name_map[key] = []
        teacher_name_map[key].append(t.id)
    
    subjects = Subject.query.all()
    for s in subjects:
        key = (s.institute_id, s.teacher_id)
        if key not in teacher_map:
            raise MigrationIntegrityError(f"Unknown teacher_id '{s.teacher_id}' for institute {s.institute_id} on Subject ID {s.id}")
        s.teacher_id_fk = teacher_map[key]
        
    courses = Course.query.all()
    course_map = {(c.institute_id, c.class_id): c.id for c in courses}
    
    # Check if SubjectCourse mappings already exist (in case of re-run)
    existing_sc = SubjectCourse.query.count()
    if existing_sc > 0:
        db.session.query(SubjectCourse).delete()
    
    for s in subjects:
        class_ids = [cid.strip() for cid in s.class_id.split(',')]
        for cid in class_ids:
            if not cid: continue
            key = (s.institute_id, cid)
            if key not in course_map:
                raise MigrationIntegrityError(f"Unknown class_id '{cid}' for institute {s.institute_id} on Subject ID {s.id}")
            cid_fk = course_map[key]
            sc = SubjectCourse(subject_id=s.id, course_id=cid_fk, is_active=True)
            db.session.add(sc)
            
    db.session.flush()

    timetables = Timetable.query.all()
    session_map = {}
    
    for tt in timetables:
        key_course = (tt.institute_id, tt.class_id)
        if key_course not in course_map:
            raise MigrationIntegrityError(f"Unknown course '{tt.class_id}' on Timetable ID {tt.id}")
        tt.course_id_fk = course_map[key_course]
        
        subject_match = None
        for s in subjects:
            if s.institute_id == tt.institute_id and s.subject_name == tt.subject_name:
                class_ids = [cid.strip() for cid in s.class_id.split(',')]
                if tt.class_id in class_ids:
                    subject_match = s
                    break
        
        if not subject_match:
            raise MigrationIntegrityError(f"Unknown subject '{tt.subject_name}' on Timetable ID {tt.id}")
        tt.subject_id_fk = subject_match.id
        
        mapped_teacher_id = None
        
        if not getattr(tt, 'is_proxy', False) and subject_match:
            mapped_teacher_id = subject_match.teacher_id_fk
        else:
            key_teacher = (tt.institute_id, tt.teacher_name)
            if key_teacher not in teacher_name_map:
                raise MigrationIntegrityError(f"Unknown teacher_name '{tt.teacher_name}' for institute {tt.institute_id} on Timetable ID {tt.id}")
            ids = teacher_name_map[key_teacher]
            if len(ids) > 1:
                raise MigrationIntegrityError(f"Ambiguous teacher_name '{tt.teacher_name}' for institute {tt.institute_id}. Multiple Teacher IDs: {ids}")
            mapped_teacher_id = ids[0]
            
        tt.teacher_id_fk = mapped_teacher_id
        
        session_key = (tt.institute_id, tt.subject_id_fk, tt.teacher_id_fk, tt.day_name, tt.start_time, tt.end_time)
        if session_key not in session_map:
            session_map[session_key] = str(uuid.uuid4())
        tt.session_group_id = session_map[session_key]

def get_stats():
    return {
        'institutes': Institute.query.count(),
        'teachers': Teacher.query.count(),
        'courses': Course.query.count(),
        'subjects': Subject.query.count(),
        'timetables': Timetable.query.count(),
        'subject_courses': SubjectCourse.query.count()
    }

def verify_migration():
    if SubjectCourse.query.count() == 0 and Subject.query.count() > 0:
        raise Exception("SubjectCourse mappings missing!")
    
    # Check orphans
    tt_nulls = Timetable.query.filter((Timetable.institute_id == None) | (Timetable.course_id_fk == None) | (Timetable.teacher_id_fk == None) | (Timetable.subject_id_fk == None)).count()
    if tt_nulls > 0:
        raise Exception(f"{tt_nulls} Timetable rows have null foreign keys.")
        
    s_nulls = Subject.query.filter(Subject.teacher_id_fk == None).count()
    if s_nulls > 0:
        raise Exception(f"{s_nulls} Subject rows have null teacher_id_fk.")

def execute():
    app = create_app() # Real application context with sqlite:///instance/autotime.db
    with app.app_context():
        print("--- BEFORE MIGRATION ---")
        stats_before = get_stats()
        for k, v in stats_before.items(): print(f"{k}: {v}")
        
        t0 = time.time()
        success = False
        try:
            with db.session.begin_nested():
                run_migration()
                db.session.flush()
                verify_migration()
            db.session.commit()
            success = True
            dur = time.time() - t0
        except Exception as e:
            db.session.rollback()
            print(f"\nMIGRATION FAILED AND ROLLED BACK: {e}")
            return
            
        if success:
            print(f"\n--- MIGRATION COMMITTED IN {dur:.4f}s ---")
            print("--- AFTER MIGRATION ---")
            stats_after = get_stats()
            for k, v in stats_after.items(): print(f"{k}: {v}")
            
            # Print a mapping sample
            tt = Timetable.query.first()
            if tt:
                print(f"\nSample Timetable: ID {tt.id}, Teacher FK {tt.teacher_id_fk}, Course FK {tt.course_id_fk}, Subject FK {tt.subject_id_fk}, Session {tt.session_group_id}")

if __name__ == '__main__':
    execute()
