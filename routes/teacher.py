from utils.timetable_helpers import build_timetable_view_model
from utils.decorators import login_required_teacher
from flask import current_app
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from models import db, Institute, Course, Subject, Teacher, Timetable, Settings, Student, TeacherUpdateRequest, AcademicCalendar, TeacherLeave, Notification
from utils.helpers import generate_institute_code, generate_and_store_otp, verify_session_otp, send_otp_email, clear_session_otp, get_dynamic_time_slots, trim_time_slots, get_val
from datetime import datetime, timedelta

from routes.blueprint import main_bp
from utils.helpers import get_dynamic_time_slots, trim_time_slots, get_val

@main_bp.route('/teacher_portal')
def teacher_portal():
    inst_code = request.args.get('inst_code')
    teacher_id = request.args.get('teacher_id')
    
    schedule = {}
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    time_slots = []
    lunch_after = 2
    teacher_name = ""
    
    if inst_code and teacher_id:
        teacher = Teacher.query.filter_by(institute_code=inst_code, teacher_id=teacher_id).first()
        if not teacher:
            flash('Invalid Institute Code or Teacher ID!', 'danger')
            return redirect(url_for('main.teacher_portal'))
            
        teacher_name = teacher.name
        time_slots = get_dynamic_time_slots(inst_code)
        settings = Settings.query.filter_by(institute_code=inst_code).all()
        s = {st.key: st.value for st in settings}
        lunch_after = int(s.get('lunch_after_lecture', 2))
        
        # Fetch timetable specifically for this teacher
        entries = Timetable.query.filter_by(institute_code=inst_code, teacher_name=teacher_name).all()
        for day in days:
            schedule[day] = {}
            for entry in entries:
                if entry.day_name == day:
                    # Teacher ko dikhna chahiye ki kis Class me lecture hai
                    schedule[day][entry.start_time] = entry

    return render_template('teacher_portal.html', schedule=schedule, days=days, time_slots=time_slots, lunch_after=lunch_after, inst_code=inst_code, teacher_id=teacher_id, teacher_name=teacher_name)

@main_bp.route('/activate_teacher', methods=['GET', 'POST'])
def activate_teacher():
    if request.method == 'POST':
        email = request.form['email'].strip()
        inst_code = request.form['inst_code'].strip()
        
        # Check agar is email aur code se koi teacher registered hai
        teacher = Teacher.query.filter_by(email=email, institute_code=inst_code).first()
        
        if not teacher:
            flash('No teacher found with this Email and Institute Code.', 'danger')
            return redirect(url_for('main.activate_teacher'))
            
        if teacher.password:
            flash('Account is already activated! Please login.', 'warning')
            return redirect(url_for('main.login_page'))

        # 6-Digit OTP Generate karo
        otp = generate_and_store_otp('activation')
        
        # Stage activation payload pending OTP verification
        session['activation_email'] = email
        session['activation_inst_code'] = inst_code
        session['activation_otp'] = otp
        
        # Send Real Email
        email_sent = send_otp_email(email, otp, context="Teacher Activation")
        
        if email_sent:
            flash('An OTP has been sent to your email address.', 'success')
        else:
            flash('Failed to send OTP email. Please try again later or contact support.', 'warning')
        return redirect(url_for('main.verify_teacher_otp'))
        
    return render_template('teacher/activate_teacher.html')

@main_bp.route('/verify_teacher_otp', methods=['GET', 'POST'])
def verify_teacher_otp():
    if 'activation_email' not in session:
        return redirect(url_for('main.activate_teacher'))
        
    if request.method == 'POST':
        user_otp = request.form['otp'].strip()
        new_password = request.form['new_password'].strip()
        
        # Verify OTP
        is_valid, msg = verify_session_otp('activation', user_otp)
        if is_valid:
            email = session.get('activation_email')
            inst_code = session.get('activation_inst_code')
            
            teacher = Teacher.query.filter_by(email=email, institute_code=inst_code).first()
            if teacher:
                # Hash and persist password
                teacher.password = generate_password_hash(new_password)
                db.session.commit()
                
                # Session se OTP data delete karo (Security)
                session.pop('activation_otp', None)
                session.pop('activation_email', None)
                session.pop('activation_inst_code', None)
                
                flash('Account Activated Successfully! You can now login.', 'success')
                return redirect(url_for('main.login_page'))
        else:
            flash(msg, 'danger')
            return redirect(url_for('main.verify_teacher_otp'))
            
    return render_template('shared/verify_otp.html', title='Verify Teacher Account', submit_url='/verify_teacher_otp', require_password=True)

@main_bp.route('/login_teacher', methods=['GET', 'POST'])
def login_teacher():
    if request.method == 'GET':
        return redirect(url_for('main.login_page'))
        
    teacher = Teacher.query.filter_by(email=request.form['email']).first()
    if teacher and teacher.password and check_password_hash(teacher.password, request.form['password']):
        session.pop('admin_id', None)
        session.pop('student_id', None)
        session['teacher_id'] = teacher.teacher_id
        session['institute_code'] = teacher.institute_code
        session['teacher_name'] = teacher.name
        session['teacher_dept'] = teacher.departments
        flash(f'Welcome to your portal, Prof. {teacher.name}!', 'success')
        return redirect(url_for('main.teacher_dash'))
    
    flash('Invalid Email/Password or Account not activated via OTP!', 'danger')
    return redirect(url_for('main.login_page'))

@main_bp.route('/teacher_dash')
@login_required_teacher
def teacher_dash():
    inst_code = session['institute_code']
    t_name = session['teacher_name']
    
    # Get dynamic time slots & settings
    time_slots = get_dynamic_time_slots(inst_code)
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get('lunch_after_lecture', 2))
    
    # 1. Fetch this specific teacher's schedule
    schedule = {day: {} for day in days}
    entries = Timetable.query.filter(
        Timetable.institute_code == inst_code,
        Timetable.teacher_name.like(f"%{t_name}%") # Matches original and proxy names
    ).all()
    
    for entry in entries:
        schedule[entry.day_name][entry.start_time] = entry

    time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    # 2. Fetch all courses for the Read-Only Viewer
    courses = Course.query.filter_by(institute_code=inst_code).all()
    
    today_str = datetime.now().strftime('%a')
    
    inst = Institute.query.filter_by(institute_code=inst_code).first()
    inst_name = inst.name if inst else "Institute"
    
    return render_template('teacher/teacher_dash.html', schedule=schedule, courses=courses, days=days, time_slots=time_slots, lunch_after=lunch_after, t_name=t_name, today_str=today_str, inst_name=inst_name)

@main_bp.route('/teacher_view_class')
@login_required_teacher
def teacher_view_class():
    inst_code = session['institute_code']
    class_id = request.args.get('class_id')
    
    if not class_id:
        # Render the class selector page instead of redirecting
        courses = Course.query.filter_by(institute_code=inst_code).all()
        return render_template('teacher/course_viewer.html', courses=courses, title='Course Viewer')
        
    schedule = {}
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    time_slots = get_dynamic_time_slots(inst_code)
    
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get('lunch_after_lecture', 2))
    
    entries = Timetable.query.filter_by(institute_code=inst_code, class_id=class_id).all()
    for day in days:
        schedule[day] = {}
        for entry in entries:
            if entry.day_name == day:
                schedule[day][entry.start_time] = entry
                
    time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    days_data = build_timetable_view_model(schedule, days, time_slots)
    return render_template('student/student_portal.html', schedule=schedule, days_data=days_data, days=days, time_slots=time_slots, lunch_after=lunch_after, inst_code=inst_code, class_id=class_id, teacher_view=True)

@main_bp.route('/apply_leave', methods=['GET', 'POST'])
def apply_leave():
    if request.method == 'GET':
        if 'teacher_id' not in session: return redirect(url_for('main.login_page'))
        inst_code = session['institute_code']
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        time_slots = get_dynamic_time_slots(inst_code)
        return render_template('teacher/apply_leave.html', days=days, time_slots=time_slots, title='Apply Leave')
        
    if 'teacher_id' not in session: return redirect(url_for('main.login_page'))
    inst_code = session['institute_code']
    leave_day = request.form['leave_day']
    leave_time = request.form.get('leave_time', 'ALL')
    # Step 0: The 1-Hour Rule Restriction
    today_str = datetime.now().strftime('%a')
    if leave_day == today_str:
        setting = Settings.query.filter_by(institute_code=inst_code, key='start_time').first()
        start_time_str = setting.value if setting else '08:00'
        start_time_obj = datetime.strptime(start_time_str, '%H:%M')
        cutoff_time = (start_time_obj - timedelta(hours=1)).time()
        
        if datetime.now().time() > cutoff_time:
            flash(f'Leave for today must be applied before {cutoff_time.strftime("%I:%M %p")}. Please contact Admin.', 'danger')
            return redirect(url_for('main.apply_leave'))

    t_name = session['teacher_name']
    t_dept = session['teacher_dept'].split(',')
    
    # Step 1: Find all lectures of this teacher on the leave day
    query = Timetable.query.filter_by(institute_code=inst_code, teacher_name=t_name, day_name=leave_day)
    if leave_time != 'ALL':
        query = query.filter_by(start_time=leave_time)
        
    my_lectures = query.all()
    
    if not my_lectures:
        time_text = f"at {leave_time}" if leave_time != 'ALL' else "on this day"
        flash(f'You have no lectures scheduled {time_text}!', 'info')
        return redirect(url_for('main.apply_leave'))
        
    # Step 2: Calculate Current Workload for Workload Balancing
    from sqlalchemy import func
    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    assigned_counts = {t.name: 0 for t in all_teachers}
    
    # Fix: Count unique slots (day + time) to avoid double counting Common subjects
    tt_entries = Timetable.query.filter_by(institute_code=inst_code).all()
    teacher_slots = {}
    for entry in tt_entries:
        base_name = entry.teacher_name.replace(" (Proxy)", "")
        teacher_slots.setdefault(base_name, set()).add((entry.day_name, entry.start_time))
        
    for name, slots in teacher_slots.items():
        if name in assigned_counts:
            assigned_counts[name] += len(slots)
            
    success_count = 0
    
    for lecture in my_lectures:
        free_candidates = []
        
        for candidate in all_teachers:
            if candidate.name == t_name: continue # Skip self
            if leave_day not in candidate.available_days: continue
            
            # BUG FIX: Max Hours Check (Prevents assigning beyond capacity)
            if assigned_counts.get(candidate.name, 0) >= candidate.max_hours: continue
            
            # Check if candidate is FREE at this exact time slot
            is_busy = Timetable.query.filter_by(institute_code=inst_code, teacher_name=candidate.name, day_name=leave_day, start_time=lecture.start_time).first()
            if not is_busy:
                # Priority factor: Same department gets a virtual reduction in workload to prioritize them slightly
                is_same_dept = any(d.strip() in candidate.departments for d in t_dept)
                virtual_workload = assigned_counts[candidate.name] - (5 if is_same_dept else 0)
                free_candidates.append((virtual_workload, candidate))
                
        if free_candidates:
            # Sort by workload (lowest first)
            free_candidates.sort(key=lambda x: x[0])
            replacement = free_candidates[0][1]
            
            # Step 3: Assign Proxy and Update Database (Dynamic Subject)
            lecture.teacher_name = f"{replacement.name} (Proxy)"
            lecture.is_proxy = True
            
            # Dynamic Subject Replacement
            # Check if proxy teaches this class
            matching_sub = Subject.query.filter_by(institute_code=inst_code, teacher_id=replacement.teacher_id).filter(Subject.class_id.contains(lecture.class_id)).first()
            if matching_sub:
                lecture.subject_name = matching_sub.subject_name
            else:
                lecture.subject_name = "Supervision (Proxy)"
                
            # Increment their workload tracking so subsequent proxies in this loop know they are busier
            assigned_counts[replacement.name] += 1
            success_count += 1
            
    db.session.commit()
    time_text = f"for {leave_time}" if leave_time != 'ALL' else f"for {leave_day}"
    flash(f'Leave applied {time_text}! Auto-Proxy successfully assigned replacements for {success_count} lectures.', 'success')
    return redirect(url_for('main.teacher_dash'))

@main_bp.route('/api/get_classes/<inst_code>')
def get_classes(inst_code):
    courses = Course.query.filter_by(institute_code=inst_code).all()
    classes = [c.class_id for c in courses]
    return jsonify({'classes': classes})
from models import Notification
@main_bp.route('/teacher_notifications')
@login_required_teacher
def teacher_notifications():
    inst_code = session['institute_code']
    t_id = session['teacher_id']
    
    notifs = Notification.query.filter_by(institute_code=inst_code, user_type='teacher', user_id=t_id).order_by(Notification.created_at.desc()).all()
    return render_template('teacher/notifications.html', notifications=notifs)
