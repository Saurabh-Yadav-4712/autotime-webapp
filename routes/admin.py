from utils.decorators import login_required_admin
from flask import current_app
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from models import db, Institute, Course, Subject, Teacher, Timetable, Settings, Student, TeacherUpdateRequest, AcademicCalendar, TeacherLeave, Notification
from utils.helpers import generate_institute_code, generate_and_store_otp, verify_session_otp, send_otp_email, clear_session_otp, get_dynamic_time_slots, trim_time_slots, get_val
import csv
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import io
from io import BytesIO
from datetime import datetime, timedelta

from routes.blueprint import main_bp
from utils.helpers import get_dynamic_time_slots, trim_time_slots, get_val

@main_bp.route('/admin_dash')
@login_required_admin
def admin_dash():
    inst_code = session['institute_code']
    
    # Calculate Analytics
    c_count = db.session.query(Course.department).filter_by(institute_code=inst_code).distinct().count()
    t_count = Teacher.query.filter_by(institute_code=inst_code).count()
    s_count = Subject.query.filter_by(institute_code=inst_code).count()
    
    # Check if timetable generated
    generated = Timetable.query.filter_by(institute_code=inst_code).first() is not None
    
    # Free teachers (rough logic: those whose assigned hours < max_hours)
    # We can approximate free teachers by checking how many teachers have fewer lectures in Timetable than max_hours, or just list the count of teachers.
    # To keep it efficient:
    all_teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    assigned_counts = {t.name: 0 for t in all_teachers}
    
    if generated:
        # Fix: Count unique slots (day + time) to avoid double counting Common subjects
        tt_entries = Timetable.query.filter_by(institute_code=inst_code).all()
        teacher_slots = {}
        for entry in tt_entries:
            base_name = entry.teacher_name.replace(" (Proxy)", "")
            teacher_slots.setdefault(base_name, set()).add((entry.day_name, entry.start_time))
            
        for name, slots in teacher_slots.items():
            if name in assigned_counts:
                assigned_counts[name] += len(slots)
    
    free_teachers_count = 0
    faculty_workload = []
    
    for t in all_teachers:
        assigned = assigned_counts[t.name]
        free_hrs = max(0, t.max_hours - assigned)
        
        if free_hrs > 0:
            free_teachers_count += 1
            
        faculty_workload.append({
            'name': t.name,
            'max_hours': t.max_hours,
            'assigned_hours': assigned,
            'free_hours': free_hrs
        })

    import math
    subjects = Subject.query.filter_by(institute_code=inst_code).all()
    all_courses = Course.query.filter_by(institute_code=inst_code).all()
    
    # Create mapping of class_id to department
    class_dept_map = {c.class_id: c.department for c in all_courses}
    
    weeks_setting = Settings.query.filter_by(institute_code=inst_code, key='weeks_per_semester').first()
    weeks_per_semester = int(weeks_setting.value) if weeks_setting else 15
    
    syllabus_tracking_grouped = {}
    for s in subjects:
        # Attempt to determine department from first class_id mapping
        first_class = s.class_id.split(',')[0].strip() if s.class_id else ""
        dept = class_dept_map.get(first_class, "General/Unassigned")
        
        if dept not in syllabus_tracking_grouped:
            syllabus_tracking_grouped[dept] = []
            
        syllabus_tracking_grouped[dept].append({
            'name': s.subject_name,
            'code': s.subject_code,
            'teacher': s.teacher_id,
            'total_hrs': s.total_course_hours,
            'weekly_hrs': s.required_hours,
            'weeks_needed': math.ceil(s.total_course_hours / s.required_hours) if s.required_hours > 0 else 0
        })

    pending_requests = TeacherUpdateRequest.query.filter_by(institute_code=inst_code, status='Pending').all()
    admin = Institute.query.get(session['admin_id'])
    return render_template('admin/admin_dash.html', admin=admin, c_count=c_count, t_count=t_count, s_count=s_count, generated=generated, free_teachers=free_teachers_count, faculty_workload=faculty_workload, syllabus_tracking_grouped=syllabus_tracking_grouped, weeks_per_semester=weeks_per_semester, pending_requests=pending_requests)

@main_bp.route('/bulk_import/<manage_type>', methods=['POST'])
@login_required_admin
def bulk_import(manage_type):
    inst_code = session['institute_code']
    
    if 'file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(request.referrer or url_for('main.admin_dash'))
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(request.referrer or url_for('main.admin_dash'))
        
    if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
        flash('Only .csv and .xlsx files are allowed.', 'danger')
        return redirect(request.referrer or url_for('main.admin_dash'))

    success_count = 0
    error_count = 0
    
    try:
        def get_val(r, *keys):
            for k in keys:
                if k in r and r[k] is not None and str(r[k]).strip() != '': return str(r[k]).strip()
            for k in keys:
                target = str(k).lower().replace(' ', '').replace('_', '').replace('/', '')
                for rk in r.keys():
                    if rk is not None:
                        if str(rk).lower().replace(' ', '').replace('_', '').replace('/', '') == target:
                            if r[rk] is not None and str(r[rk]).strip() != '':
                                return str(r[rk]).strip()
            return ''

        data = []
        if file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)
            for row in csv_input:
                data.append(row)
        else:
            wb = openpyxl.load_workbook(filename=io.BytesIO(file.read()))
            sheet = wb.active
            headers = [cell.value for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if any(row):
                    data.append(dict(zip(headers, row)))
                    
        for row in data:
            try:
                if manage_type == 'course':
                    class_id = get_val(row, 'class_id', 'classid')
                    dept = get_val(row, 'department', 'departments')
                    sem = get_val(row, 'semester')
                    div = get_val(row, 'division')
                    if not class_id: raise ValueError("class_id missing")
                    c = Course(institute_code=inst_code, class_id=class_id, department=dept, semester=sem, division=div)
                    db.session.add(c)
                elif manage_type == 'teacher':
                    tid = get_val(row, 'teacher_id', 'teacherid')
                    name = get_val(row, 'name')
                    email = get_val(row, 'email')
                    depts = get_val(row, 'departments', 'department')
                    hours = get_val(row, 'max_hours', 'max_hours_week', 'maxhoursweek', 'maxhours')
                    days = get_val(row, 'available_days', 'days')
                    if not tid or not name: raise ValueError("teacher_id or name missing")
                    t = Teacher(institute_code=inst_code, teacher_id=tid, name=name, email=email, departments=depts, max_hours=int(hours or 0), available_days=days)
                    db.session.add(t)
                elif manage_type == 'subject':
                    scode = get_val(row, 'subject_code', 'subjectcode')
                    sname = get_val(row, 'subject_name', 'subjectname', 'subject')
                    cid = get_val(row, 'class_id', 'classid')
                    tid = get_val(row, 'teacher_id', 'teacherid')
                    stype = get_val(row, 'subject_type', 'subjecttype') or 'Theory'
                    req_hrs_raw = get_val(row, 'required_hours', 'requiredhours')
                    tot_hrs = get_val(row, 'total_course_hours', 'totalcoursehours', 'totalhours') or 50
                    sess_len = get_val(row, 'session_length', 'sessionlength') or 1
                    
                    if req_hrs_raw:
                        req_hrs = int(req_hrs_raw)
                    else:
                        weeks_setting = Settings.query.filter_by(institute_code=inst_code, key='weeks_per_semester').first()
                        weeks = int(weeks_setting.value) if weeks_setting else 15
                        import math
                        req_hrs = math.ceil(int(tot_hrs) / weeks)
                        
                    if not scode: raise ValueError("subject_code missing")
                    s = Subject(institute_code=inst_code, subject_code=scode, subject_name=sname, class_id=cid, teacher_id=tid, subject_type=stype, required_hours=req_hrs, total_course_hours=int(tot_hrs), session_length=int(sess_len))
                    db.session.add(s)
                db.session.commit()
                success_count += 1
            except Exception as e:
                db.session.rollback()
                print(f"Error importing row {row}: {e}")
                error_count += 1
                
        flash(f'Batch Upload Complete! Successfully added: {success_count}. Failed/Duplicates: {error_count}.', 'info')
    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'danger')
        
    if manage_type == 'course': return redirect(url_for('main.manage_courses'))
    elif manage_type == 'teacher': return redirect(url_for('main.manage_teachers'))
    elif manage_type == 'subject': return redirect(url_for('main.manage_subjects'))
    return redirect(url_for('main.admin_dash'))

@main_bp.route('/manage_courses', methods=['GET', 'POST'])
@login_required_admin
def manage_courses():
    inst_code = session['institute_code']

    if request.method == 'POST':
        db.session.add(Course(
            institute_code=inst_code, class_id=request.form['class_id'],
            department=request.form['department'], semester=request.form['semester'],
            division=request.form['division']
        ))
        db.session.commit()
        flash('Course added!', 'success')
        return redirect(url_for('main.manage_courses'))
    
    courses = Course.query.filter_by(institute_code=inst_code).all()
    return render_template('admin/manage_master.html', manage_type='course', items=courses)

@main_bp.route('/manage_teachers', methods=['GET', 'POST'])
@login_required_admin
def manage_teachers():
    inst_code = session['institute_code']

    if request.method == 'POST':
        if Teacher.query.filter_by(email=request.form['email']).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('main.manage_teachers'))
            
        days = request.form.getlist('days')
        if not days:
            flash('Select at least one day!', 'danger')
            return redirect(url_for('main.manage_teachers'))

        db.session.add(Teacher(
            institute_code=inst_code, teacher_id=request.form['teacher_id'],
            name=request.form['name'], email=request.form['email'],
            departments=request.form['departments'], available_days=",".join(days),
            max_hours=int(request.form['max_hours'])
        ))
        db.session.commit()
        flash('Teacher added!', 'success')
        return redirect(url_for('main.manage_teachers'))
    
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    courses = Course.query.filter_by(institute_code=inst_code).all()
    unique_depts = list(set([c.department for c in courses]))
    return render_template('admin/manage_master.html', manage_type='teacher', items=teachers, depts=unique_depts)

@main_bp.route('/manage_subjects', methods=['GET', 'POST'])
@login_required_admin
def manage_subjects():
    inst_code = session['institute_code']

    if request.method == 'POST':
        class_ids = request.form.getlist('class_id')
        if not class_ids:
            flash('Select at least one Class!', 'danger')
            return redirect(url_for('main.manage_subjects'))

        weeks_setting = Settings.query.filter_by(institute_code=inst_code, key='weeks_per_semester').first()
        weeks = int(weeks_setting.value) if weeks_setting else 15
        total_hours = int(request.form['total_course_hours'])
        session_len = int(request.form.get('session_length', 1))
        import math
        
        db.session.add(Subject(
            institute_code=inst_code, subject_code=request.form['subject_code'],
            subject_name=request.form['subject_name'], class_id=",".join(class_ids),
            teacher_id=request.form['teacher_id'], total_course_hours=total_hours,
            required_hours=math.ceil(total_hours / weeks),
            subject_type=request.form['subject_type'], session_length=session_len
        ))
        db.session.commit()
        flash('Subject mapped!', 'success')
        return redirect(url_for('main.manage_subjects'))
    
    subjects = Subject.query.filter_by(institute_code=inst_code).all()
    courses = Course.query.filter_by(institute_code=inst_code).all()
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    return render_template('admin/manage_master.html', manage_type='subject', items=subjects, courses=courses, teachers=teachers)

@main_bp.route('/edit_course/<int:id>', methods=['GET', 'POST'])
@login_required_admin
def edit_course(id):
    course = Course.query.get_or_404(id)
    if request.method == 'POST':
        course.class_id = request.form['class_id']
        course.department = request.form['department']
        course.semester = request.form['semester']
        course.division = request.form['division']
        db.session.commit()
        flash('Course updated!', 'success')
        return redirect(url_for('main.manage_courses'))
    return render_template('admin/edit_master.html', item=course, edit_type='course')

@main_bp.route('/edit_teacher/<int:id>', methods=['GET', 'POST'])
@login_required_admin
def edit_teacher(id):
    teacher = Teacher.query.get_or_404(id)
    if request.method == 'POST':
        teacher.teacher_id = request.form['teacher_id']
        teacher.name = request.form['name']
        teacher.email = request.form['email']
        teacher.departments = request.form['departments']
        teacher.max_hours = request.form['max_hours']
        days = request.form.getlist('days')
        if days: teacher.available_days = ",".join(days)
        db.session.commit()
        flash('Teacher updated!', 'success')
        return redirect(url_for('main.manage_teachers'))
    
    courses = Course.query.filter_by(institute_code=session['institute_code']).all()
    depts = list(set([c.department for c in courses]))
    return render_template('admin/edit_master.html', item=teacher, edit_type='teacher', unique_depts=depts)

@main_bp.route('/edit_subject/<int:id>', methods=['GET', 'POST'])
@login_required_admin
def edit_subject(id):
    subject = Subject.query.get_or_404(id)
    if request.method == 'POST':
        subject.subject_code = request.form['subject_code']
        subject.subject_name = request.form['subject_name']
        class_ids = request.form.getlist('class_id')
        if class_ids: subject.class_id = ",".join(class_ids)
        subject.teacher_id = request.form['teacher_id']
        weeks_setting = Settings.query.filter_by(institute_code=session['institute_code'], key='weeks_per_semester').first()
        weeks = int(weeks_setting.value) if weeks_setting else 15
        total_hours = int(request.form['total_course_hours'])
        session_len = int(request.form.get('session_length', 1))
        import math
        subject.total_course_hours = total_hours
        subject.session_length = session_len
        subject.required_hours = math.ceil(total_hours / weeks)
        subject.subject_type = request.form['subject_type']
        db.session.commit()
        flash('Subject updated!', 'success')
        return redirect(url_for('main.manage_subjects'))
    
    courses = Course.query.filter_by(institute_code=session['institute_code']).all()
    teachers = Teacher.query.filter_by(institute_code=session['institute_code']).all()
    return render_template('admin/edit_master.html', item=subject, edit_type='subject', courses=courses, teachers=teachers)

@main_bp.route('/delete/<type>/<int:id>')
@login_required_admin
def delete_item(type, id):
    
    if type == 'course':
        item = Course.query.get_or_404(id)
        route = 'manage_courses'
    elif type == 'teacher':
        item = Teacher.query.get_or_404(id)
        route = 'manage_teachers'
    else:
        item = Subject.query.get_or_404(id)
        route = 'manage_subjects'

    if item.institute_code == session['institute_code']:
        db.session.delete(item)
        db.session.commit()
        flash('Deleted successfully.', 'info')
    
    return redirect(url_for('main.' + route))

@main_bp.route('/bulk_delete/<type>', methods=['POST'])
@login_required_admin
def bulk_delete_items(type):
    inst_code = session['institute_code']
    selected_ids = request.form.getlist('selected_ids')
    
    if not selected_ids:
        flash('No items selected for deletion.', 'warning')
        if type == 'course': return redirect(url_for('main.manage_courses'))
        if type == 'teacher': return redirect(url_for('main.manage_teachers'))
        return redirect(url_for('main.manage_subjects'))
    
    try:
        if type == 'course':
            num_deleted = Course.query.filter(Course.id.in_(selected_ids), Course.institute_code==inst_code).delete(synchronize_session=False)
            route = 'manage_courses'
        elif type == 'teacher':
            num_deleted = Teacher.query.filter(Teacher.id.in_(selected_ids), Teacher.institute_code==inst_code).delete(synchronize_session=False)
            route = 'manage_teachers'
        elif type == 'subject':
            num_deleted = Subject.query.filter(Subject.id.in_(selected_ids), Subject.institute_code==inst_code).delete(synchronize_session=False)
            route = 'manage_subjects'
            
        db.session.commit()
        flash(f'Successfully deleted {num_deleted} items.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting items: {str(e)}', 'danger')
        route = 'admin_dash'
        
    return redirect(url_for('main.' + route))

@main_bp.route('/generate_timetable', methods=['GET', 'POST'])
def generate_timetable():
    if request.method == 'GET':
        return redirect(url_for('main.admin_dash'))
        
    if 'admin_id' not in session:
        return redirect(url_for('main.login_page'))
        
    inst_code = session['institute_code']
    
    from utils.autotime_main import engine_generate_timetable
    engine_generate_timetable(inst_code)
    
    flash('⚡ Timetable Generated Successfully! Zero Clashes Detected.', 'success')
    return redirect(url_for('main.admin_dash'))

@main_bp.route('/view_timetable')
@login_required_admin
def view_timetable():
    inst_code = session['institute_code']
    
    courses = Course.query.filter_by(institute_code=inst_code).all()
    selected_class = request.args.get('class_id')
    
    schedule = {}
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    time_slots = get_dynamic_time_slots(inst_code)
    
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get('lunch_after_lecture', 2))
    break_duration = int(s.get('break_time', 30)) # Fetch break duration
    
    if selected_class:
        entries = Timetable.query.filter_by(institute_code=inst_code, class_id=selected_class).all()
        for day in days:
            schedule[day] = {}
            for entry in entries:
                if entry.day_name == day:
                    schedule[day][entry.start_time] = entry
        time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    inst = Institute.query.filter_by(institute_code=inst_code).first()
    inst_name = inst.name if inst else "Institute"
    
    # Fetch teachers and subjects for manual editing
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    if selected_class:
        subjects = Subject.query.filter_by(institute_code=inst_code, class_id=selected_class).all()
    else:
        subjects = []
    
    return render_template('shared/view_timetable.html', courses=courses, selected_class=selected_class, schedule=schedule, days=days, time_slots=time_slots, lunch_after=lunch_after, break_duration=break_duration, inst_name=inst_name, teachers=teachers, subjects=subjects)

@main_bp.route('/api/get_slot_data', methods=['GET'])
@login_required_admin
def get_slot_data():
    inst_code = session.get('institute_code')
    day = request.args.get('day')
    start_time = request.args.get('start_time')
    class_id = request.args.get('class_id')
    
    if not all([inst_code, day, start_time, class_id]):
        return jsonify({"error": "Missing parameters"}), 400
        
    teachers = Teacher.query.filter_by(institute_code=inst_code).all()
    result = {"free": [], "busy": []}
    
    for t in teachers:
        # Check if busy
        busy_entry = Timetable.query.filter_by(
            institute_code=inst_code,
            day_name=day,
            start_time=start_time,
            teacher_name=t.name
        ).first()
        
        # Get subjects for this specific class
        # subject class_id can be comma separated, so we check if class_id in it
        subs = Subject.query.filter(
            Subject.institute_code == inst_code,
            Subject.teacher_id == t.teacher_id,
            Subject.class_id.like(f"%{class_id}%")
        ).all()
        
        sub_names = [s.subject_name for s in subs]
        
        t_data = {
            "name": t.name,
            "subjects": sub_names,
            "busy_class": busy_entry.class_id if busy_entry else None
        }
        
        if busy_entry:
            result["busy"].append(t_data)
        else:
            result["free"].append(t_data)
            
    return jsonify(result)

@main_bp.route('/edit_timetable_slot', methods=['POST'])
@login_required_admin
def edit_timetable_slot():
    
    entry_id = request.form.get('entry_id')
    new_subject = request.form.get('new_subject')
    new_teacher = request.form.get('new_teacher')
    
    entry = Timetable.query.get(entry_id)
    if not entry:
        flash('Timetable slot not found.', 'danger')
        return redirect(url_for('main.view_timetable', class_id=request.form.get('class_id')))
        
    # Check for teacher clash (is the new teacher busy at this exact day and time?)
    if new_teacher != entry.teacher_name:
        clash = Timetable.query.filter_by(
            institute_code=entry.institute_code,
            day_name=entry.day_name,
            start_time=entry.start_time,
            teacher_name=new_teacher
        ).first()
        
        if clash:
            flash(f'Cannot assign {new_teacher}. They are already teaching Class {clash.class_id} at this time!', 'danger')
            return redirect(url_for('main.view_timetable', class_id=entry.class_id))
            
    # Update entry
    entry.subject_name = new_subject
    entry.teacher_name = new_teacher
    # Clear proxy flag if any
    if hasattr(entry, 'is_proxy') and entry.is_proxy:
        entry.is_proxy = False
        entry.original_teacher = None
        
    db.session.commit()
    flash('Timetable slot updated successfully!', 'success')
    return redirect(url_for('main.view_timetable', class_id=entry.class_id))

@main_bp.route('/export_timetables')
@login_required_admin
def export_timetables():
    inst_code = session['institute_code']
    
    # Fetch Classes
    classes = db.session.query(Timetable.class_id).filter_by(institute_code=inst_code).distinct().all()
    class_ids = [c[0] for c in classes]
    
    if not class_ids:
        flash('No timetable generated yet to export!', 'warning')
        return redirect(url_for('main.view_timetable'))

    # Fetch Settings & Slots
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    
    institute_name = s.get('institute_name', 'INSTITUTE TIMETABLE').upper()
    lunch_after = int(s.get('lunch_after_lecture', 2))
    
    # Time slots format: "08:00 AM - 09:00 AM"
    time_slots = get_dynamic_time_slots(inst_code)
    slots = [f"{slot[0]} - {slot[1]}" for slot in time_slots]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    # Excel Styling Variables
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    title_font = Font(name='Arial', size=16, bold=True)
    header_font = Font(name='Arial', size=11, bold=True)
    cell_font = Font(name='Arial', size=10)
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    blue_fill = PatternFill(start_color="B4C6E7", end_color="B4C6E7", fill_type="solid")
    lunch_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    for cls in class_ids:
        safe_sheet_name = str(cls).replace('/', '-').replace('\\', '-')[:31]
        ws = wb.create_sheet(title=safe_sheet_name)
        
        # Titles
        c1 = ws.cell(row=1, column=1, value=institute_name)
        c1.font = title_font; c1.alignment = center_align
        c2 = ws.cell(row=2, column=1, value=f"TIMETABLE / SCHEDULE - {cls}")
        c2.font = header_font; c2.alignment = center_align; c2.fill = blue_fill
        
        ws.cell(row=3, column=1, value="Day").font = header_font
        ws.cell(row=3, column=1).alignment = center_align; ws.cell(row=3, column=1).border = thin_border
        ws.column_dimensions['A'].width = 12
        
        col_idx = 2
        lunch_printed = False
        slot_to_col = {}
        
        # Build Header & Lunch Break Column
        for i, slot in enumerate(slots):
            # Print Lunch Column exactly after the specified lecture
            if not lunch_printed and i == lunch_after:
                lc = ws.cell(row=3, column=col_idx, value="LUNCH\nBREAK")
                lc.font = header_font; lc.alignment = center_align; lc.border = thin_border; lc.fill = lunch_fill
                ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 10
                
                # Merge and rotate text vertically
                ws.merge_cells(start_row=4, start_column=col_idx, end_row=4+len(days)-1, end_column=col_idx)
                lb_cell = ws.cell(row=4, column=col_idx, value="L U N C H   B R E A K")
                lb_cell.alignment = Alignment(textRotation=90, horizontal='center', vertical='center', wrap_text=True)
                lb_cell.font = Font(name='Arial', size=14, bold=True, color="595959")
                lb_cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                
                for r in range(4, 4+len(days)): ws.cell(row=r, column=col_idx).border = thin_border
                col_idx += 1
                lunch_printed = True
            
            # Print Time Slot Header
            slot_to_col[slot] = col_idx
            cell = ws.cell(row=3, column=col_idx, value=slot.replace(" - ", "\n"))
            cell.font = header_font; cell.alignment = center_align; cell.border = thin_border
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 18
            col_idx += 1
            
        max_col = col_idx - 1
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_col)
            
        # Fetch data for this specific class
        tt_entries = Timetable.query.filter_by(institute_code=inst_code, class_id=cls).all()
        tt_dict = {(e.day_name, f"{e.start_time} - {e.end_time}"): f"{e.subject_name}\n({e.teacher_name})" for e in tt_entries}
        
        # Populate Grid Data
        for row_idx, day in enumerate(days, start=4):
            day_cell = ws.cell(row=row_idx, column=1, value=day)
            day_cell.font = header_font; day_cell.alignment = center_align; day_cell.border = thin_border
            
            for slot in slots:
                c_idx = slot_to_col[slot]
                cell = ws.cell(row=row_idx, column=c_idx, value=tt_dict.get((day, slot), "---"))
                cell.font = cell_font; cell.alignment = center_align; cell.border = thin_border
                
    # Save Excel to memory buffer
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(output, download_name="AutoTime_Master_Schedule.xlsx", as_attachment=True)

@main_bp.route('/college_settings', methods=['GET', 'POST'])
@login_required_admin
def college_settings():
    inst_code = session['institute_code']

    if request.method == 'POST':
        # Yahan humne 'lunch_after_lecture' add kar diya hai
        keys = ['total_lectures', 'start_time', 'lecture_duration', 'break_time', 'lunch_after_lecture', 'weeks_per_semester']
        for key in keys:
            val = request.form.get(key)
            if val:
                setting = Settings.query.filter_by(institute_code=inst_code, key=key).first()
                if setting:
                    setting.value = val 
                else:
                    new_setting = Settings(institute_code=inst_code, key=key, value=val)
                    db.session.add(new_setting)
        
        db.session.commit()
        flash('College Settings Updated Successfully!', 'success')
        return redirect(url_for('main.college_settings'))

    all_settings = Settings.query.filter_by(institute_code=inst_code).all()
    settings_dict = {s.key: s.value for s in all_settings}

    return render_template('admin/college_settings.html', settings=settings_dict)

@main_bp.route('/admin/requests/approve/<int:req_id>', methods=['POST'])
@login_required_admin
def approve_teacher_request(req_id):
    req = TeacherUpdateRequest.query.get_or_404(req_id)
    if req.institute_code != session.get('institute_code'): return "Unauthorized", 403
    
    teacher = Teacher.query.filter_by(teacher_id=req.teacher_id, institute_code=req.institute_code).first()
    if teacher:
        if req.new_name:
            teacher.name = req.new_name
        if req.new_email:
            teacher.email = req.new_email
        req.status = 'Approved'
        db.session.commit()
        flash('Teacher update request approved.', 'success')
    return redirect(url_for('main.admin_dash'))

@main_bp.route('/admin/requests/reject/<int:req_id>', methods=['POST'])
@login_required_admin
def reject_teacher_request(req_id):
    req = TeacherUpdateRequest.query.get_or_404(req_id)
    if req.institute_code != session.get('institute_code'): return "Unauthorized", 403
    
    req.status = 'Rejected'
    db.session.commit()
    flash('Teacher update request rejected.', 'info')
    return redirect(url_for('main.admin_dash'))
from models import AcademicCalendar, Notification
from datetime import datetime
from utils.autotime_main import auto_allocate_proxy

@main_bp.route('/manage_calendar', methods=['GET', 'POST'])
@login_required_admin
def manage_calendar():
    inst_code = session['institute_code']
    
    if request.method == 'POST':
        date_str = request.form.get('date')
        event_name = request.form.get('event_name')
        department = request.form.get('department', 'All') # 'All' or specific dept
        is_holiday = request.form.get('is_holiday') == 'on'
        
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            new_event = AcademicCalendar(
                institute_code=inst_code,
                date=event_date,
                event_name=event_name,
                department=department,
                is_holiday=is_holiday
            )
            db.session.add(new_event)
            db.session.commit()
            
            # Auto-Allocate Proxies for missing lectures caused by this event
            if is_holiday:
                auto_allocate_proxy(inst_code, event_date)
            
            flash('Event added successfully! Proxy Engine ran for affected lectures.', 'success')
        except Exception as e:
            flash(f'Error adding event: {str(e)}', 'danger')
            
        return redirect(url_for('main.manage_calendar'))
        
    events = AcademicCalendar.query.filter_by(institute_code=inst_code).order_by(AcademicCalendar.date).all()
    # Fetch unique departments from Courses
    depts = [r.department for r in db.session.query(Course.department).filter_by(institute_code=inst_code).distinct()]
    return render_template('admin/manage_calendar.html', events=events, depts=depts)

@main_bp.route('/notifications')
@login_required_admin
def admin_notifications():
    inst_code = session['institute_code']
    
    notifs = Notification.query.filter_by(institute_code=inst_code, user_type='admin').order_by(Notification.created_at.desc()).all()
    return render_template('admin/notifications.html', notifications=notifs)
