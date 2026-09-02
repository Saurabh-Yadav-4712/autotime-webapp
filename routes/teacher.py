from utils.timetable_helpers import build_timetable_view_model
from utils.decorators import login_required_teacher
from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from models import Course, Institute, Notification, Settings, Teacher, TeacherLeave, Timetable, db
from utils.helpers import (
    generate_and_store_otp,
    get_dynamic_time_slots,
    is_valid_email,
    normalize_email,
    send_otp_email,
    trim_time_slots,
    validate_password,
    verify_session_otp,
)
from utils.security import begin_authenticated_session
from datetime import datetime, timedelta

from routes.blueprint import main_bp


@main_bp.route("/teacher_portal")
def teacher_portal():
    inst_code = request.args.get("inst_code")
    teacher_id = request.args.get("teacher_id")

    schedule = {}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    time_slots = []
    lunch_after = 2
    teacher_name = ""

    if inst_code and teacher_id:
        teacher = Teacher.query.filter_by(institute_code=inst_code, teacher_id=teacher_id).first()
        if not teacher:
            flash("Invalid Institute Code or Teacher ID!", "danger")
            return redirect(url_for("main.teacher_portal"))

        teacher_name = teacher.name
        time_slots = get_dynamic_time_slots(inst_code)
        settings = Settings.query.filter_by(institute_code=inst_code).all()
        s = {st.key: st.value for st in settings}
        lunch_after = int(s.get("lunch_after_lecture", 2))

        entries = Timetable.query.filter_by(
            institute_code=inst_code, teacher_name=teacher_name
        ).all()
        schedule = {day: {} for day in days}
        for entry in entries:
            if entry.day_name in schedule:
                schedule[entry.day_name][entry.start_time] = entry

    return render_template(
        "teacher/teacher_dash.html",
        schedule=schedule,
        days=days,
        time_slots=time_slots,
        lunch_after=lunch_after,
        t_name=teacher_name,
        selected_date=None,
        today_str=datetime.now().strftime("%a"),
    )


@main_bp.route("/activate_teacher", methods=["GET", "POST"])
def activate_teacher():
    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        inst_code = request.form.get("inst_code", "").strip().upper()
        if not is_valid_email(email):
            flash("Enter a valid email address.", "danger")
            return redirect(url_for("main.activate_teacher"))

        # Match the invitation within the supplied institute.
        teacher = Teacher.query.filter_by(email=email, institute_code=inst_code).first()

        if not teacher:
            flash("No teacher found with this Email and Institute Code.", "danger")
            return redirect(url_for("main.activate_teacher"))

        if teacher.password:
            flash("Account is already activated! Please login.", "warning")
            return redirect(url_for("main.login_page"))

        otp = generate_and_store_otp("activation")

        # Stage activation payload pending OTP verification
        session["activation_email"] = email
        session["activation_inst_code"] = inst_code

        # Send Real Email
        email_sent = send_otp_email(email, otp, context="Teacher Activation")

        if email_sent:
            flash("An OTP has been sent to your email address.", "success")
        else:
            flash("Failed to send OTP email. Please try again later or contact support.", "warning")
        return redirect(url_for("main.verify_teacher_otp"))

    return render_template("teacher/activate_teacher.html")


@main_bp.route("/verify_teacher_otp", methods=["GET", "POST"])
def verify_teacher_otp():
    if "activation_email" not in session:
        return redirect(url_for("main.activate_teacher"))

    if request.method == "POST":
        user_otp = request.form["otp"].strip()
        new_password = request.form["new_password"].strip()
        password_is_valid, password_error = validate_password(new_password)
        if not password_is_valid:
            flash(password_error, "danger")
            return redirect(url_for("main.verify_teacher_otp"))

        is_valid, msg = verify_session_otp("activation", user_otp)
        if is_valid:
            email = session.get("activation_email")
            inst_code = session.get("activation_inst_code")

            teacher = Teacher.query.filter_by(email=email, institute_code=inst_code).first()
            if teacher:
                teacher.password = generate_password_hash(new_password)
                db.session.commit()

                session.pop("activation_email", None)
                session.pop("activation_inst_code", None)

                flash("Account Activated Successfully! You can now login.", "success")
                return redirect(url_for("main.login_page"))
        else:
            flash(msg, "danger")
            return redirect(url_for("main.verify_teacher_otp"))

    return render_template(
        "shared/verify_otp.html",
        title="Verify Teacher Account",
        submit_url="/verify_teacher_otp",
        require_password=True,
    )


@main_bp.route("/login_teacher", methods=["GET", "POST"])
def login_teacher():
    if request.method == "GET":
        return redirect(url_for("main.login_page"))

    email = normalize_email(request.form.get("email"))
    teacher = Teacher.query.filter_by(email=email).first()
    password = request.form.get("password", "")
    if teacher and teacher.password and check_password_hash(teacher.password, password):
        begin_authenticated_session(
            teacher_id=teacher.teacher_id,
            institute_code=teacher.institute_code,
            teacher_name=teacher.name,
            teacher_dept=teacher.departments,
        )
        flash(f"Welcome to your portal, Prof. {teacher.name}!", "success")
        return redirect(url_for("main.teacher_dash"))

    flash("Invalid Email/Password or Account not activated via OTP!", "danger")
    return redirect(url_for("main.login_page"))


@main_bp.route("/teacher_dash")
@login_required_teacher
def teacher_dash():
    inst_code = session["institute_code"]
    t_name = session["teacher_name"]

    selected_date_str = request.args.get("date")
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Get dynamic time slots & settings
    time_slots = get_dynamic_time_slots(inst_code)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get("lunch_after_lecture", 2))

    # 1. Fetch this specific teacher's schedule
    schedule = {day: {} for day in days}
    from utils.timetable_adapter import get_effective_timetable

    all_entries = get_effective_timetable(inst_code, {}, selected_date)
    entries = [e for e in all_entries if e.teacher_name == t_name]

    for entry in entries:
        schedule[entry.day_name][entry.start_time] = entry

    time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    # 2. Fetch all courses for the Read-Only Viewer
    courses = Course.query.filter_by(institute_code=inst_code).all()

    today_str = datetime.now().strftime("%a")

    inst = Institute.query.filter_by(institute_code=inst_code).first()
    inst_name = inst.name if inst else "Institute"

    return render_template(
        "teacher/teacher_dash.html",
        schedule=schedule,
        selected_date=selected_date_str,
        courses=courses,
        days=days,
        time_slots=time_slots,
        lunch_after=lunch_after,
        t_name=t_name,
        today_str=today_str,
        inst_name=inst_name,
    )


@main_bp.route("/teacher_view_class")
@login_required_teacher
def teacher_view_class():
    inst_code = session["institute_code"]
    class_id = request.args.get("class_id")
    selected_date_str = request.args.get("date")
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if not class_id:
        # Render the class selector page instead of redirecting
        courses = Course.query.filter_by(institute_code=inst_code).all()
        return render_template("teacher/course_viewer.html", courses=courses, title="Course Viewer")

    schedule = {}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    time_slots = get_dynamic_time_slots(inst_code)

    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get("lunch_after_lecture", 2))

    from utils.timetable_adapter import get_effective_timetable

    entries = get_effective_timetable(inst_code, {"class_id": class_id}, selected_date)
    for day in days:
        schedule[day] = {}
        for entry in entries:
            if entry.day_name == day:
                schedule[day][entry.start_time] = entry

    time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    days_data = build_timetable_view_model(schedule, days, time_slots)
    return render_template(
        "student/student_portal.html",
        schedule=schedule,
        selected_date=selected_date_str,
        days_data=days_data,
        days=days,
        time_slots=time_slots,
        lunch_after=lunch_after,
        inst_code=inst_code,
        class_id=class_id,
        teacher_view=True,
    )


@main_bp.route("/apply_leave", methods=["GET", "POST"])
@login_required_teacher
def apply_leave():
    if request.method == "GET":
        inst_code = session["institute_code"]
        time_slots = get_dynamic_time_slots(inst_code)
        today_date = datetime.now().strftime("%Y-%m-%d")
        return render_template(
            "teacher/apply_leave.html",
            time_slots=time_slots,
            today_date=today_date,
            title="Apply Leave",
        )

    inst_code = session["institute_code"]
    leave_date_str = request.form["leave_date"]
    leave_time = request.form.get("leave_time", "ALL")

    try:
        leave_date = datetime.strptime(leave_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for("main.apply_leave"))

    # Step 0: The 1-Hour Rule Restriction for today
    today_date = datetime.now().date()
    if leave_date == today_date:
        setting = Settings.query.filter_by(institute_code=inst_code, key="start_time").first()
        start_time_str = setting.value if setting else "08:00"
        start_time_obj = datetime.strptime(start_time_str, "%H:%M")
        cutoff_time = (start_time_obj - timedelta(hours=1)).time()

        if datetime.now().time() > cutoff_time:
            flash(
                f"Leave for today must be applied before {cutoff_time.strftime('%I:%M %p')}. Please contact Admin.",
                "danger",
            )
            return redirect(url_for("main.apply_leave"))
    elif leave_date < today_date:
        flash("Cannot apply for leave in the past.", "danger")
        return redirect(url_for("main.apply_leave"))

    t_id = session["teacher_id"]
    t_name = session["teacher_name"]

    # Check if a pending or approved request already exists
    existing = TeacherLeave.query.filter_by(
        institute_code=inst_code,
        teacher_id=t_id,
        date=leave_date,
        start_time=leave_time if leave_time != "ALL" else None,
    ).first()

    if existing:
        flash("You have already applied for leave on this date/time.", "warning")
        return redirect(url_for("main.apply_leave"))

    # Create the TeacherLeave record
    leave = TeacherLeave(
        institute_code=inst_code,
        teacher_id=t_id,
        date=leave_date,
        start_time=leave_time if leave_time != "ALL" else None,
        status="Pending",
    )
    db.session.add(leave)

    # Notify the Admin
    date_formatted = leave_date.strftime("%d %b %Y")
    time_text = f"at {leave_time}" if leave_time != "ALL" else "for the full day"
    msg_admin = f"{t_name} requested leave for {date_formatted} {time_text}."
    notif = Notification(institute_code=inst_code, user_type="admin", message=msg_admin)
    db.session.add(notif)

    db.session.commit()

    flash("Leave request submitted successfully. Waiting for Admin approval.", "success")
    return redirect(url_for("main.teacher_dash"))


@main_bp.route("/teacher/cancel_leave/<int:leave_id>", methods=["POST"])
@login_required_teacher
def teacher_cancel_leave(leave_id):
    from utils.leave_service import cancel_leave

    success, msg = cancel_leave(
        leave_id,
        actor_name=session["teacher_name"],
        institute_code=session["institute_code"],
        teacher_id=session["teacher_id"],
    )
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("main.teacher_dash"))


@main_bp.route("/api/get_classes/<inst_code>")
def get_classes(inst_code):
    courses = Course.query.filter_by(institute_code=inst_code).all()
    grouped_classes = {}
    for c in courses:
        dept = c.department or "General"
        if dept not in grouped_classes:
            grouped_classes[dept] = []
        grouped_classes[dept].append(c.class_id)

    classes = [c.class_id for c in courses]
    return jsonify({"grouped_classes": grouped_classes, "classes": classes})


from models import Notification


@main_bp.route("/teacher_notifications")
@login_required_teacher
def teacher_notifications():
    inst_code = session["institute_code"]
    t_id = session["teacher_id"]

    notifs = (
        Notification.query.filter_by(institute_code=inst_code, user_type="teacher", user_id=t_id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("teacher/notifications.html", notifications=notifs)
