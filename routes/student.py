from utils.timetable_helpers import build_timetable_view_model
from utils.decorators import login_required_student
from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from models import Course, Institute, Settings, Student, Teacher, db
from utils.helpers import (
    generate_and_store_otp,
    get_dynamic_time_slots,
    is_valid_email,
    normalize_email,
    send_otp_email,
    trim_time_slots,
    validate_password,
)
from utils.security import begin_authenticated_session
from datetime import datetime

from routes.blueprint import main_bp


@main_bp.route("/student_portal")
def student_portal():
    inst_code = request.args.get("inst_code")
    class_id = request.args.get("class_id")
    selected_date_str = request.args.get("date")
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    schedule = {}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    time_slots = []
    lunch_after = 2

    if inst_code and class_id:
        # Check if institute exists
        institute = Institute.query.filter_by(institute_code=inst_code).first()
        if not institute:
            flash("Invalid Institute Code!", "danger")
            return redirect(url_for("main.student_portal"))

        time_slots = get_dynamic_time_slots(inst_code)
        settings = Settings.query.filter_by(institute_code=inst_code).all()
        s = {st.key: st.value for st in settings}
        lunch_after = int(s.get("lunch_after_lecture", 2))

        from utils.timetable_adapter import get_effective_timetable

        entries = get_effective_timetable(inst_code, {"class_id": class_id}, selected_date)
        schedule = {day: {} for day in days}
        for entry in entries:
            if entry.day_name in schedule:
                schedule[entry.day_name][entry.start_time] = entry

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
    )


@main_bp.route("/register_student", methods=["GET", "POST"])
def register_student():
    if request.method == "POST":
        inst_code = request.form["inst_code"].strip().upper()
        name = request.form["name"].strip()
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        class_id = request.form.get("class_id", "").strip()

        # Institute check
        institute = Institute.query.filter_by(institute_code=inst_code).first()
        if not institute:
            flash("Invalid Institute Code!", "danger")
            return redirect(url_for("main.register_student"))

        # Class check
        course = Course.query.filter_by(institute_code=inst_code, class_id=class_id).first()
        if not course:
            flash(f"Invalid Class ID for Institute {inst_code}!", "danger")
            return redirect(url_for("main.register_student"))

        if not name or not is_valid_email(email):
            flash("Enter a valid name and email address.", "danger")
            return redirect(url_for("main.register_student"))
        password_is_valid, password_error = validate_password(password)
        if not password_is_valid:
            flash(password_error, "danger")
            return redirect(url_for("main.register_student"))

        if (
            Student.query.filter_by(email=email).first()
            or Institute.query.filter_by(admin_email=email).first()
            or Teacher.query.filter_by(email=email).first()
        ):
            flash("Email already registered! Please login.", "warning")
            return redirect(url_for("main.login_page"))

        # Generate OTP and store in session
        otp = generate_and_store_otp("reg")
        session["reg_data"] = {
            "type": "student",
            "inst_code": inst_code,
            "name": name,
            "email": email,
            "class_id": class_id,
            "password_hash": generate_password_hash(password),
        }

        email_sent = send_otp_email(email, otp, context="Student Registration")
        if not email_sent:
            flash("Failed to send OTP email. Please try again later or contact support.", "warning")
        else:
            flash("An OTP has been sent to your email for verification.", "info")
        return redirect(url_for("main.verify_reg_otp"))

    return render_template("auth/register_student.html")


@main_bp.route("/login_student", methods=["GET", "POST"])
def login_student():
    if request.method == "GET":
        return redirect(url_for("main.login_page"))

    email = normalize_email(request.form.get("email"))
    student = Student.query.filter_by(email=email).first()
    password = request.form.get("password", "")
    if student and check_password_hash(student.password, password):
        begin_authenticated_session(
            student_id=student.id,
            institute_code=student.institute_code,
            student_name=student.name,
            student_class=student.class_id,
        )
        flash(f"Welcome to your Live Timetable, {student.name}!", "success")
        return redirect(url_for("main.student_dash"))

    flash("Invalid Email or Password!", "danger")
    return redirect(url_for("main.login_page"))


@main_bp.route("/student_dash")
@login_required_student
def student_dash():
    inst_code = session["institute_code"]
    class_id = session["student_class"]
    s_name = session["student_name"]

    selected_date_str = request.args.get("date")
    selected_date = None
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    time_slots = get_dynamic_time_slots(inst_code)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get("lunch_after_lecture", 2))

    schedule = {day: {} for day in days}
    from utils.timetable_adapter import get_effective_timetable

    entries = get_effective_timetable(inst_code, {"class_id": class_id}, selected_date)

    for entry in entries:
        schedule[entry.day_name][entry.start_time] = entry

    inst = Institute.query.filter_by(institute_code=inst_code).first()
    inst_name = inst.name if inst else "Institute"
    today_str = datetime.now().strftime("%a")
    time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    return render_template(
        "student/student_dash.html",
        schedule=schedule,
        selected_date=selected_date_str,
        days=days,
        time_slots=time_slots,
        lunch_after=lunch_after,
        s_name=s_name,
        class_id=class_id,
        today_str=today_str,
        inst_name=inst_name,
    )
