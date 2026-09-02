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
    from utils.helpers import ScheduleConfig, get_local_date
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = get_local_date()
    else:
        selected_date = get_local_date()

    schedule = {}
    day_dates = {}

    if inst_code:
        schedule_config = ScheduleConfig(inst_code)
        days = schedule_config.working_days
        time_slots = schedule_config.get_dynamic_time_slots()
        lunch_after = schedule_config.lunch_after
    else:
        days = []
        time_slots = []
        lunch_after = 2

    if inst_code and class_id:
        institute = Institute.query.filter_by(institute_code=inst_code).first()
        if not institute:
            flash("Invalid Institute Code!", "danger")
            return redirect(url_for("main.student_portal"))

        from utils.timetable_adapter import get_live_week_timetable

        live_week = get_live_week_timetable(inst_code, reference_date=selected_date, filters={"class_id": class_id})
        days = live_week["working_days"]
        day_dates = live_week["day_dates"]

        schedule = {day: {} for day in days}
        for entry in live_week["records"]:
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
        day_dates=day_dates,
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
    from utils.helpers import ScheduleConfig, get_local_date
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = get_local_date()
    else:
        selected_date = get_local_date()

    schedule_config = ScheduleConfig(inst_code)
    time_slots = schedule_config.get_dynamic_time_slots()
    lunch_after = schedule_config.lunch_after

    from utils.timetable_adapter import get_live_week_timetable

    live_week = get_live_week_timetable(inst_code, reference_date=selected_date, filters={"class_id": class_id})
    days = live_week["working_days"]
    day_dates = live_week["day_dates"]

    schedule = {day: {} for day in days}
    for entry in live_week["records"]:
        schedule[entry.day_name][entry.start_time] = entry

    inst = Institute.query.filter_by(institute_code=inst_code).first()
    inst_name = inst.name if inst else "Institute"
    today_str = get_local_date().strftime("%a")
    time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    return render_template(
        "student/student_dash.html",
        schedule=schedule,
        selected_date=selected_date_str,
        days=days,
        day_dates=day_dates,
        time_slots=time_slots,
        lunch_after=lunch_after,
        s_name=s_name,
        class_id=class_id,
        today_str=today_str,
        inst_name=inst_name,
    )
