import re

from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    AcademicCalendar,
    Course,
    GenerationHistory,
    Institute,
    Notification,
    Settings,
    Student,
    Subject,
    Teacher,
    TeacherLeave,
    TeacherUpdateRequest,
    Timetable,
    db,
)
from utils.helpers import (
    generate_and_store_otp,
    generate_institute_code,
    is_valid_email,
    normalize_email,
    send_otp_email,
    validate_password,
    verify_session_otp,
)
from utils.security import begin_authenticated_session

from routes.blueprint import main_bp

INSTITUTE_CODE_PATTERN = re.compile(r"^[A-Z0-9-]{3,20}$")


def _generate_unique_institute_code():
    for _ in range(10):
        code = generate_institute_code()
        if not Institute.query.filter_by(institute_code=code).first():
            return code
    raise RuntimeError("Unable to generate a unique institute code")


def redirect_if_authenticated():
    if "admin_id" in session:
        return redirect(url_for("main.admin_dash"))
    if "teacher_id" in session:
        return redirect(url_for("main.teacher_dash"))
    if "student_id" in session:
        return redirect(url_for("main.student_dash"))
    return None


@main_bp.route("/")
def home():
    if red := redirect_if_authenticated():
        return red
    return render_template("main_site/landing.html")


@main_bp.route("/login")
def login_page():
    if red := redirect_if_authenticated():
        return red
    return render_template("auth/auth.html")


@main_bp.route("/register_institute", methods=["GET", "POST"])
def register_institute():
    if red := redirect_if_authenticated():
        return red
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = normalize_email(request.form.get("email"))
        college_name = request.form.get("college_name", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not college_name or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for("main.register_institute"))
        if not is_valid_email(email):
            flash("Enter a valid email address.", "danger")
            return redirect(url_for("main.register_institute"))
        password_is_valid, password_error = validate_password(password)
        if not password_is_valid:
            flash(password_error, "danger")
            return redirect(url_for("main.register_institute"))
        if Institute.query.filter_by(admin_username=username).first():
            flash("Username already exists.", "danger")
            return redirect(url_for("main.register_institute"))
        if (
            Institute.query.filter_by(admin_email=email).first()
            or Teacher.query.filter_by(email=email).first()
            or Student.query.filter_by(email=email).first()
        ):
            flash("Email already registered.", "danger")
            return redirect(url_for("main.register_institute"))

        # Stage registration payload pending OTP verification
        otp = generate_and_store_otp("reg")
        session["reg_data"] = {
            "type": "institute",
            "college_name": college_name,
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
        }

        email_sent = send_otp_email(email, otp, context="Institute Registration")
        if not email_sent:
            flash("Failed to send OTP email. Please try again later or contact support.", "warning")
        else:
            flash("An OTP has been sent to your email for verification.", "info")
        return redirect(url_for("main.verify_reg_otp"))
    return render_template("auth/register_institute.html")


@main_bp.route("/verify_reg_otp", methods=["GET", "POST"])
def verify_reg_otp():
    if red := redirect_if_authenticated():
        return red
    if "reg_data" not in session or "reg_otp" not in session:
        flash("Session expired. Please register again.", "danger")
        return redirect(url_for("main.login_page"))

    if request.method == "POST":
        user_otp = request.form["otp"].strip()
        is_valid, msg = verify_session_otp("reg", user_otp)

        if is_valid:
            data = session["reg_data"]

            if data["type"] == "institute":
                inst_code = _generate_unique_institute_code()
                new_institute = Institute(
                    name=data["college_name"],
                    institute_code=inst_code,
                    admin_username=data["username"],
                    admin_email=data["email"],
                    admin_password=data["password_hash"],
                )
                db.session.add(new_institute)
                db.session.commit()

                # Clear session
                session.pop("reg_data", None)

                flash(
                    f"College Registered Successfully! Your Institute Code is: {inst_code}",
                    "success",
                )
                return redirect(url_for("main.login_page"))

            elif data["type"] == "student":
                new_student = Student(
                    institute_code=data["inst_code"],
                    name=data["name"],
                    email=data["email"],
                    class_id=data["class_id"],
                    password=data["password_hash"],
                )
                db.session.add(new_student)
                db.session.commit()

                session.pop("reg_data", None)

                flash("Student Registered Successfully! You can now login.", "success")
                return redirect(url_for("main.login_page"))

        else:
            flash(msg, "danger")
            return redirect(url_for("main.verify_reg_otp"))

    return render_template(
        "shared/verify_otp.html", title="Verify Registration", submit_url="/verify_reg_otp"
    )


@main_bp.route("/login_admin", methods=["GET", "POST"])
def login_admin():
    if request.method == "GET":
        return redirect(url_for("main.login_page"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Username and password are required!", "danger")
        return redirect(url_for("main.login_page"))

    admin = Institute.query.filter_by(admin_username=username).first()
    if admin and check_password_hash(admin.admin_password, password):
        begin_authenticated_session(
            admin_id=admin.id,
            institute_code=admin.institute_code,
        )
        flash(f"Welcome back, {admin.name}!", "success")
        return redirect(url_for("main.admin_dash"))
    flash("Invalid Credentials!", "danger")
    return redirect(url_for("main.login_page"))


@main_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.login_page"))


@main_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    email = normalize_email(request.form.get("email"))
    if not is_valid_email(email):
        flash("If that address belongs to an account, a verification code was sent.", "info")
        return redirect(url_for("main.reset_password"))

    target = None
    user = Institute.query.filter_by(admin_email=email).first()
    if user:
        target = {"role": "admin", "id": user.id, "email": email}
    else:
        user = Teacher.query.filter_by(email=email).first()
        if user:
            target = {"role": "teacher", "id": user.id, "email": email}
        else:
            user = Student.query.filter_by(email=email).first()
            if user:
                target = {"role": "student", "id": user.id, "email": email}

    otp = generate_and_store_otp("password_reset")
    session["password_reset_target"] = target
    if target:
        send_otp_email(email, otp, context="Password Reset")

    flash("If that address belongs to an account, a verification code was sent.", "info")
    return redirect(url_for("main.reset_password"))


@main_bp.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if "password_reset_otp" not in session or "password_reset_target" not in session:
        flash("Request a new password reset code.", "warning")
        return redirect(url_for("main.forgot_password"))

    if request.method == "GET":
        return render_template("auth/reset_password.html")

    new_password = request.form.get("new_password", "")
    password_is_valid, password_error = validate_password(new_password)
    if not password_is_valid:
        flash(password_error, "danger")
        return redirect(url_for("main.reset_password"))

    is_valid, message = verify_session_otp("password_reset", request.form.get("otp", "").strip())
    target = session.get("password_reset_target")
    if not is_valid or not target:
        flash(message if not is_valid else "Invalid password reset request.", "danger")
        return redirect(url_for("main.forgot_password"))

    role = target.get("role")
    if role == "admin":
        user = Institute.query.filter_by(id=target["id"], admin_email=target["email"]).first()
        password_field = "admin_password"
    elif role == "teacher":
        user = Teacher.query.filter_by(id=target["id"], email=target["email"]).first()
        password_field = "password"
    elif role == "student":
        user = Student.query.filter_by(id=target["id"], email=target["email"]).first()
        password_field = "password"
    else:
        user = None
        password_field = None

    if not user:
        session.pop("password_reset_target", None)
        flash("Invalid password reset request.", "danger")
        return redirect(url_for("main.forgot_password"))

    setattr(user, password_field, generate_password_hash(new_password))
    db.session.commit()
    session.clear()
    flash("Password reset successfully. You can now sign in.", "success")
    return redirect(url_for("main.login_page"))


@main_bp.route("/settings")
def settings():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        flash("Please login to access settings.", "danger")
        return redirect(url_for("main.login_page"))

    user_role = ""
    user_info = {}

    if "admin_id" in session:
        user_role = "admin"
        inst = db.session.get(Institute, session["admin_id"])
        user_info = {
            "name": inst.name,
            "email": inst.admin_email,
            "institute_code": inst.institute_code,
        }
    elif "teacher_id" in session:
        user_role = "teacher"
        t = Teacher.query.filter_by(
            teacher_id=session["teacher_id"],
            institute_code=session["institute_code"],
        ).first()
        user_info = {"name": t.name, "email": t.email, "institute_code": t.institute_code}
    elif "student_id" in session:
        user_role = "student"
        s = db.session.get(Student, session["student_id"])
        user_info = {"name": s.name, "email": s.email, "institute_code": s.institute_code}

    return render_template("shared/settings.html", user_role=user_role, user_info=user_info)


@main_bp.route("/settings/update_profile", methods=["POST"])
def update_profile():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        return redirect(url_for("main.login_page"))

    new_name = request.form.get("name", "").strip()
    new_email = normalize_email(request.form.get("email"))

    if not new_name or not new_email:
        flash("Name and Email cannot be empty.", "danger")
        return redirect(url_for("main.settings"))
    if not is_valid_email(new_email):
        flash("Enter a valid email address.", "danger")
        return redirect(url_for("main.settings"))

    if "admin_id" in session:
        role = "admin"
        user = db.session.get(Institute, session["admin_id"])
        current_email = normalize_email(user.admin_email) if user else None
        new_code = request.form.get("institute_code", "").strip().upper()
    elif "teacher_id" in session:
        role = "teacher"
        user = Teacher.query.filter_by(
            teacher_id=session["teacher_id"],
            institute_code=session["institute_code"],
        ).first()
        current_email = normalize_email(user.email) if user else None
        new_code = None
    else:
        role = "student"
        user = db.session.get(Student, session["student_id"])
        current_email = normalize_email(user.email) if user else None
        new_code = None

    if not user:
        session.clear()
        flash("Your session is no longer valid. Please sign in again.", "warning")
        return redirect(url_for("main.login_page"))

    if new_email != current_email:
        if (
            Institute.query.filter_by(admin_email=new_email).first()
            or Teacher.query.filter_by(email=new_email).first()
            or Student.query.filter_by(email=new_email).first()
        ):
            flash("This email is already in use.", "danger")
            return redirect(url_for("main.settings"))

    if role == "teacher":
        if new_name == user.name and new_email == current_email:
            flash("No changes made.", "info")
            return redirect(url_for("main.settings"))
        existing_request = TeacherUpdateRequest.query.filter_by(
            institute_code=user.institute_code,
            teacher_id=user.teacher_id,
            status="Pending",
        ).first()
        if existing_request:
            flash("You already have a pending profile update request.", "warning")
            return redirect(url_for("main.settings"))
        db.session.add(
            TeacherUpdateRequest(
                institute_code=user.institute_code,
                teacher_id=user.teacher_id,
                new_name=new_name if new_name != user.name else None,
                new_email=new_email if new_email != current_email else None,
            )
        )
        db.session.add(
            Notification(
                institute_code=user.institute_code,
                user_type="admin",
                message=f"Teacher {user.name} requested a profile update.",
            )
        )
        db.session.commit()
        flash("Profile update request sent to admin for approval.", "success")
        return redirect(url_for("main.settings"))

    if role == "admin":
        if not new_code or not INSTITUTE_CODE_PATTERN.fullmatch(new_code):
            flash("Institute code must be 3-20 letters, numbers, or hyphens.", "danger")
            return redirect(url_for("main.settings"))
        code_owner = Institute.query.filter_by(institute_code=new_code).first()
        if code_owner and code_owner.id != user.id:
            flash("Institute Code already taken by another institute.", "danger")
            return redirect(url_for("main.settings"))

    if new_email != current_email:
        otp = generate_and_store_otp("email_update")
        if send_otp_email(new_email, otp, context="Email Update"):
            session["pending_profile_update"] = {
                "email": new_email,
                "name": new_name,
                "role": role,
                "institute_code": new_code,
            }
            return redirect(url_for("main.verify_email_update"))
        flash("Failed to send verification email. Please try again.", "danger")
        return redirect(url_for("main.settings"))

    user.name = new_name
    if role == "admin" and new_code != user.institute_code:
        _update_institute_code(user, new_code)
    db.session.commit()

    flash("Profile updated successfully!", "success")
    return redirect(url_for("main.settings"))


def _update_institute_code(institute, new_code):
    old_code = institute.institute_code
    models_with_legacy_code = (
        Teacher,
        Student,
        Course,
        Subject,
        Timetable,
        Settings,
        TeacherUpdateRequest,
        AcademicCalendar,
        TeacherLeave,
        Notification,
        GenerationHistory,
    )
    for model in models_with_legacy_code:
        model.query.filter_by(institute_code=old_code).update(
            {"institute_code": new_code}, synchronize_session=False
        )
    institute.institute_code = new_code
    session["institute_code"] = new_code


@main_bp.route("/verify_email_update", methods=["GET", "POST"])
def verify_email_update():
    if "pending_profile_update" not in session or "email_update_otp" not in session:
        flash("No pending email update found.", "warning")
        return redirect(url_for("main.settings"))

    if request.method == "POST":
        user_otp = request.form.get("otp", "").strip()
        is_valid, msg = verify_session_otp("email_update", user_otp)
        if is_valid:
            pending = session["pending_profile_update"]
            new_email = pending["email"]
            role = pending["role"]

            if role == "admin" and "admin_id" in session:
                user = db.session.get(Institute, session["admin_id"])
                user.admin_email = new_email
            elif role == "student" and "student_id" in session:
                user = db.session.get(Student, session["student_id"])
                user.email = new_email
            else:
                session.pop("pending_profile_update", None)
                flash("Your session changed. Please submit the update again.", "warning")
                return redirect(url_for("main.settings"))

            user.name = pending["name"]
            if role == "admin" and pending.get("institute_code") != user.institute_code:
                _update_institute_code(user, pending["institute_code"])
            db.session.commit()
            session.pop("pending_profile_update", None)
            flash("Email successfully updated!", "success")
            return redirect(url_for("main.settings"))
        flash(msg, "danger")

    return render_template(
        "shared/verify_otp.html", title="Verify Email Update", submit_url="/verify_email_update"
    )


@main_bp.route("/settings/change_password", methods=["POST"])
def settings_change_password():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        return redirect(url_for("main.login_page"))

    old_pass = request.form["current_password"]
    new_pass = request.form["new_password"]
    password_is_valid, password_error = validate_password(new_pass)
    if not password_is_valid:
        flash(password_error, "danger")
        return redirect(url_for("main.settings"))

    if "admin_id" in session:
        user = db.session.get(Institute, session["admin_id"])
        if check_password_hash(user.admin_password, old_pass):
            user.admin_password = generate_password_hash(new_pass)
            db.session.commit()
            flash("Password changed successfully!", "success")
            return redirect(url_for("main.settings"))
    elif "teacher_id" in session:
        user = Teacher.query.filter_by(
            teacher_id=session["teacher_id"],
            institute_code=session["institute_code"],
        ).first()
        if user and check_password_hash(user.password, old_pass):
            user.password = generate_password_hash(new_pass)
            db.session.commit()
            flash("Password changed successfully!", "success")
            return redirect(url_for("main.settings"))
    elif "student_id" in session:
        user = db.session.get(Student, session["student_id"])
        if user and check_password_hash(user.password, old_pass):
            user.password = generate_password_hash(new_pass)
            db.session.commit()
            flash("Password changed successfully!", "success")
            return redirect(url_for("main.settings"))

    flash("Incorrect current password.", "danger")
    return redirect(url_for("main.settings"))


@main_bp.route("/settings/delete_account")
def delete_account_page():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        return redirect(url_for("main.login_page"))
    return render_template("shared/delete_account.html")


@main_bp.route("/settings/delete_account/send_otp", methods=["POST"])
def delete_account_send_otp():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        return redirect(url_for("main.login_page"))

    password = request.form.get("password")
    is_valid = False
    email = None

    if "admin_id" in session:
        user = db.session.get(Institute, session["admin_id"])
        email = user.admin_email
        is_valid = check_password_hash(user.admin_password, password)
    elif "teacher_id" in session:
        user = Teacher.query.filter_by(
            teacher_id=session["teacher_id"], institute_code=session["institute_code"]
        ).first()
        email = user.email
        is_valid = check_password_hash(user.password, password) if user.password else False
    elif "student_id" in session:
        user = db.session.get(Student, session["student_id"])
        email = user.email
        is_valid = check_password_hash(user.password, password)

    if not is_valid:
        flash("Incorrect current password.", "danger")
        return redirect(url_for("main.delete_account_page"))

    otp = generate_and_store_otp("delete_account")
    if send_otp_email(email, otp, context="Account Deletion"):
        return redirect(url_for("main.verify_delete_account_page"))
    else:
        flash("Failed to send verification email. Please try again.", "danger")
        return redirect(url_for("main.delete_account_page"))


@main_bp.route("/settings/delete_account/verify")
def verify_delete_account_page():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        return redirect(url_for("main.login_page"))
    if "delete_account_otp" not in session:
        return redirect(url_for("main.delete_account_page"))
    return render_template(
        "shared/verify_otp.html",
        title="Confirm Deletion",
        message="Enter the 6-digit OTP sent to your email to confirm deletion. This cannot be undone.",
        submit_url="/settings/delete_account/confirm",
        btn_text="Permanently Delete Account",
    )


@main_bp.route("/settings/delete_account/confirm", methods=["POST"])
def delete_account_confirm():
    if "admin_id" not in session and "teacher_id" not in session and "student_id" not in session:
        return redirect(url_for("main.login_page"))
    if "delete_account_otp" not in session:
        return redirect(url_for("main.delete_account_page"))

    user_otp = request.form.get("otp", "").strip()
    is_valid, msg = verify_session_otp("delete_account", user_otp)
    if not is_valid:
        flash(msg, "danger")
        return redirect(url_for("main.verify_delete_account_page"))

    # Process Deletion based on role
    if "admin_id" in session:
        inst_code = session["institute_code"]
        # Delete legacy rows in dependency order; relational rows also cascade.
        Timetable.query.filter_by(institute_code=inst_code).delete()
        TeacherLeave.query.filter_by(institute_code=inst_code).delete()
        Subject.query.filter_by(institute_code=inst_code).delete()
        Teacher.query.filter_by(institute_code=inst_code).delete()
        Course.query.filter_by(institute_code=inst_code).delete()
        Settings.query.filter_by(institute_code=inst_code).delete()
        Student.query.filter_by(institute_code=inst_code).delete()
        TeacherUpdateRequest.query.filter_by(institute_code=inst_code).delete()
        AcademicCalendar.query.filter_by(institute_code=inst_code).delete()
        Notification.query.filter_by(institute_code=inst_code).delete()
        GenerationHistory.query.filter_by(institute_code=inst_code).delete()
        Institute.query.filter_by(institute_code=inst_code).delete()
        db.session.commit()
        flash("Institute and all associated data have been permanently deleted.", "success")

    elif "teacher_id" in session:
        user = Teacher.query.filter_by(
            teacher_id=session["teacher_id"], institute_code=session["institute_code"]
        ).first()
        if user:
            user.password = None
            db.session.commit()
            flash("Your account login has been deactivated. You can re-activate later.", "success")

    elif "student_id" in session:
        user = db.session.get(Student, session["student_id"])
        if user:
            db.session.delete(user)
            db.session.commit()
            flash("Your account has been permanently deleted.", "success")

    session.clear()
    return redirect(url_for("main.home"))
